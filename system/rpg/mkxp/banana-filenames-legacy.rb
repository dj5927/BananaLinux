# Ruby 1.8 / 1.9 compatible read-only resource adapter. No modern keyword
# arguments or Module#prepend. Do not redirect writes or save paths.
STDOUT.sync = true
STDERR.sync = true
puts "[MKXP] Ruby #{RUBY_VERSION} (#{RUBY_PLATFORM})"
load ENV['BANANA_MKXP_WIN32_PRELOAD'] if ENV['BANANA_MKXP_WIN32_PRELOAD'] && File.file?(ENV['BANANA_MKXP_WIN32_PRELOAD'])
begin
  load ENV['BANANA_MKXP_COMPAT_PRELOAD'] if ENV['BANANA_MKXP_COMPAT_PRELOAD'] && File.file?(ENV['BANANA_MKXP_COMPAT_PRELOAD'])
rescue StandardError, ScriptError => e
  warn("[MKXP compat] optional preload failed: #{e.class}: #{e.message}")
end
module BananaLegacyResource
  EXISTS = File.method(:exist?)
  def self.resolve(path, directory = false)
    return path unless path.is_a?(String)
    return path if EXISTS.call(path)
    target = directory ? System.rpgmp_resource_disk_directory(path) : System.rpgmp_resource_disk_path(path)
    target || path
  rescue StandardError
    path
  end
  def self.read_only(mode)
    return true if mode.nil?
    if mode.is_a?(Integer)
      flags = File::WRONLY | File::RDWR | File::CREAT | File::TRUNC | File::APPEND
      return (mode & flags) == 0
    end
    mode.is_a?(String) && mode[0,1] == 'r' && !mode.include?('+')
  end
end
class << File
  alias_method :banana_original_open, :open
  alias_method :banana_original_new, :new
  alias_method :banana_original_read, :read
  alias_method :banana_original_exist, :exist?
  alias_method :banana_original_file, :file?
  alias_method :banana_original_directory, :directory?
  def open(path, *args, &block)
    path = BananaLegacyResource.resolve(path) if BananaLegacyResource.read_only(args[0])
    banana_original_open(path, *args, &block)
  end
  def new(path, *args, &block)
    path = BananaLegacyResource.resolve(path) if BananaLegacyResource.read_only(args[0])
    banana_original_new(path, *args, &block)
  end
  def read(path, *args)
    banana_original_read(BananaLegacyResource.resolve(path), *args)
  end
  if method_defined?(:binread)
    alias_method :banana_original_binread, :binread
    def binread(path, *args)
      banana_original_binread(BananaLegacyResource.resolve(path), *args)
    end
  end
  def exist?(path)
    banana_original_exist(path) || banana_original_exist(BananaLegacyResource.resolve(path)) || banana_original_exist(BananaLegacyResource.resolve(path,true))
  end
  alias_method :exists?, :exist?
  def file?(path)
    banana_original_file(path) || banana_original_file(BananaLegacyResource.resolve(path))
  end
  def directory?(path)
    banana_original_directory(path) || banana_original_directory(BananaLegacyResource.resolve(path,true))
  end
end
class << FileTest
  def exist?(path); File.exist?(path); end
  alias_method :exists?, :exist?
  def file?(path); File.file?(path); end
  def directory?(path); File.directory?(path); end
end
class << Dir
  alias_method :banana_original_entries, :entries
  def entries(path, *args)
    banana_original_entries(BananaLegacyResource.resolve(path,true), *args)
  end
end
class << Graphics
  unless method_defined?(:banana_supervisor_original_update)
    alias_method :banana_supervisor_original_update, :update
    def update(*args, &block)
      result = banana_supervisor_original_update(*args, &block)
      unless @banana_supervisor_ready
        marker = ENV['BANANA_MKXP_READY_FILE']
        if marker && !marker.empty?
          begin
            File.open(marker, 'wb') { |f| f.write("frame\n") }
            @banana_supervisor_ready = true
          rescue StandardError => e
            warn("Banana MKXP readiness marker: #{e.class}: #{e.message}")
            @banana_supervisor_ready = true
          end
        end
      end
      result
    end
  end
end
