// EasyCast (Claude): asynchronous DRM presentation.
// The render thread no longer waits for the GPU and for the page flip inside VulkanContext::Present():
// it hands (image, fence) to this thread and goes on with the next frame (TA processing etc.).
// An image is reused only after it left the screen: it is "in use" from submit until a later flip completed.
// EASYCAST_ASYNC_PRESENT=0 restores the synchronous path (for A/B tests in one binary).
#pragma once
#include <condition_variable>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <mutex>
#include <pthread.h>
#include <stdexcept>
#include <thread>

class EasycastAsyncPresent {
public:
	static bool enabled()
	{
		static int e = [] { const char *v = std::getenv("EASYCAST_ASYNC_PRESENT"); return v && !std::strcmp(v, "0") ? 0 : 1; }();
		return e != 0;
	}

	// render thread: queue an image whose GPU work is signalled by fence
	void submit(vk::Device device, unsigned index, vk::Fence fence)
	{
		std::unique_lock<std::mutex> lk(m);
		if (!worker.joinable()) {
			stopping = false;
			dev = device;
			worker = std::thread([this] { run(); });
		}
		inUse[index % MAX] = true;
		jobs.push_back({ index, fence });
		cv.notify_all();
	}

    // Fast-forward may drop only presentation, never reuse a busy scanout.
    bool canSubmit(unsigned index)
    {
        std::lock_guard<std::mutex> lk(m);
        // Let the normal Present() error recovery run if the worker failed.
        return failed || !inUse[index % MAX];
    }

	// render thread: before reusing an image for a new frame
	void waitFree(unsigned index)
	{
		std::unique_lock<std::mutex> lk(m);
		freed.wait(lk, [&] { return !inUse[index % MAX] || failed; });
	}

	// true once if the worker hit an error (caller recreates the swap chain)
	bool takeError()
	{
		std::lock_guard<std::mutex> lk(m);
		bool f = failed;
		failed = false;
		return f;
	}

	// stop the worker and forget all state (before buffers are recreated/destroyed)
	void stop()
	{
		{
			std::lock_guard<std::mutex> lk(m);
			stopping = true;
			cv.notify_all();
		}
		if (worker.joinable())
			worker.join();
		std::lock_guard<std::mutex> lk(m);
		jobs.clear();
		for (auto &u : inUse) u = false;
		onScreen = pendingIdx = -1;
		stopping = false;
		failed = false;
		freed.notify_all();
	}

	~EasycastAsyncPresent() { stop(); }

private:
	static constexpr unsigned MAX = 8;
	struct Job { unsigned index; vk::Fence fence; };

	void release(int idx)
	{
		if (idx >= 0) inUse[idx] = false;
	}

	void run()
	{
		pthread_setname_np(pthread_self(), "Flycast-present");
		std::unique_lock<std::mutex> lk(m);
		for (;;) {
			cv.wait(lk, [&] { return stopping || !jobs.empty(); });
			if (jobs.empty() && stopping)
				break;
			Job job = jobs.front();
			jobs.pop_front();
			lk.unlock();
			bool ok = true;
			try {
				// 1) previous flip finished -> the image shown before it is free
				easycastDrm->waitFlipPublic();
				lk.lock();
				if (pendingIdx >= 0) { release(onScreen); onScreen = pendingIdx; pendingIdx = -1; }
				freed.notify_all();
				lk.unlock();
				// 2) wait for this frame's GPU work, then show it
				vk::Result r = dev.waitForFences(job.fence, true, 2000000000ULL);
				if (r != vk::Result::eSuccess) throw std::runtime_error("DRM render fence timeout");
				const bool wasModeset = easycastDrm->isModeset();
				easycastDrm->present(job.index);
				lk.lock();
				if (!wasModeset) { release(onScreen); onScreen = (int)job.index; }   // initial SetCrtc shows at once
				else pendingIdx = (int)job.index;                                    // flip completes at next vblank
				freed.notify_all();
				lk.unlock();
			} catch (const std::exception &e) {
				std::fprintf(stderr, "EASYCAST_ASYNC_PRESENT error: %s\n", e.what());
				ok = false;
			}
			lk.lock();
			if (!ok) {
				failed = true;
				jobs.clear();
				for (auto &u : inUse) u = false;
				onScreen = pendingIdx = -1;
				freed.notify_all();
			}
		}
	}

	std::mutex m;
	std::condition_variable cv, freed;
	std::deque<Job> jobs;
	std::thread worker;
	vk::Device dev;
	bool inUse[MAX] {};
	int onScreen = -1, pendingIdx = -1;
	bool stopping = false, failed = false;
};
static EasycastAsyncPresent easycastAsync;
