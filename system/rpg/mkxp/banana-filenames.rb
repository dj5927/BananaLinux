# BananaOS native MKXP: Windows-compatible read-only resource paths.
# Keep writes, absolute paths, and paths outside resource directories untouched.
STDOUT.sync = true
STDERR.sync = true
puts "[MKXP] Ruby #{RUBY_VERSION} (#{RUBY_PLATFORM})"
load ENV['BANANA_MKXP_WIN32_PRELOAD'] if ENV['BANANA_MKXP_WIN32_PRELOAD'] && File.file?(ENV['BANANA_MKXP_WIN32_PRELOAD'])

# Ruby 3.2 removed these legacy APIs, which were already no-ops in 3.1.
# Do not reintroduce security-sensitive $SAFE behavior.
class Object
  def taint; self; end unless method_defined?(:taint)
  def untaint; self; end unless method_defined?(:untaint)
  def tainted?; false; end unless method_defined?(:tainted?)
  def trust; self; end unless method_defined?(:trust)
  def untrust; self; end unless method_defined?(:untrust)
  def untrusted?; false; end unless method_defined?(:untrusted?)
  alias_method :id, :object_id unless method_defined?(:id)
  alias_method :type, :class unless method_defined?(:type)
  TRUE = true unless const_defined?(:TRUE)
  FALSE = false unless const_defined?(:FALSE)
  NIL = nil unless const_defined?(:NIL)
end
class Hash
  alias_method :index, :key unless method_defined?(:index)
end
class << Dir
  alias_method :exists?, :exist? unless method_defined?(:exists?)
end

module BananaResourceNames
  ORIGINAL_EXISTS = File.method(:exist?)
  ORIGINAL_FILE = File.method(:file?)
  ORIGINAL_DIRECTORY = File.method(:directory?)
  def self.path(value, directory = false)
    return value unless value.is_a?(String)
    return value if ORIGINAL_EXISTS.call(value)
    resolved = directory ? System.rpgmp_resource_disk_directory(value) : System.rpgmp_resource_disk_path(value)
    resolved || value
  rescue StandardError
    value
  end
  def self.read_only?(args, kwargs)
    return false if kwargs.key?(:open_args)
    mode = kwargs.fetch(:mode, args.empty? ? 'r' : args[0])
    flags = kwargs.fetch(:flags, 0)
    forbidden = File::WRONLY | File::RDWR | File::CREAT | File::TRUNC | File::APPEND
    return false unless flags.is_a?(Integer) && (flags & forbidden).zero?
    return (mode & forbidden).zero? if mode.is_a?(Integer)
    mode.is_a?(String) && mode.start_with?('r') && !mode.include?('+')
  end
  module FileReads
    def open(path, *args, **kwargs, &block)
      path = BananaResourceNames.path(path) if BananaResourceNames.read_only?(args, kwargs)
      super(path, *args, **kwargs, &block)
    end
    def new(path, *args, **kwargs, &block)
      path = BananaResourceNames.path(path) if BananaResourceNames.read_only?(args, kwargs)
      super(path, *args, **kwargs, &block)
    end
    def read(path, *args, **kwargs)
      path = BananaResourceNames.path(path) if BananaResourceNames.read_only?([], kwargs)
      super(path, *args, **kwargs)
    end
    def binread(path, *args, **kwargs)
      super(BananaResourceNames.path(path), *args, **kwargs)
    end
    def exist?(path)
      super(path) || super(BananaResourceNames.path(path)) || super(BananaResourceNames.path(path,true))
    end
    def exists?(path)
      exist?(path)
    end
    def file?(path)
      super(path) || super(BananaResourceNames.path(path))
    end
    def directory?(path)
      super(path) || super(BananaResourceNames.path(path,true))
    end
  end
  module FileTestReads
    def exist?(path); File.exist?(path); end
    def exists?(path); File.exist?(path); end
    def file?(path); File.file?(path); end
    def directory?(path); File.directory?(path); end
  end
  module DirReads
    def entries(path, *args, **kwargs)
      super(BananaResourceNames.path(path,true), *args, **kwargs)
    end
    def children(path, *args, **kwargs)
      super(BananaResourceNames.path(path,true), *args, **kwargs)
    end
  end
end
File.singleton_class.prepend(BananaResourceNames::FileReads) unless File.singleton_class.ancestors.include?(BananaResourceNames::FileReads)
FileTest.singleton_class.prepend(BananaResourceNames::FileTestReads) unless FileTest.singleton_class.ancestors.include?(BananaResourceNames::FileTestReads)
Dir.singleton_class.prepend(BananaResourceNames::DirReads) unless Dir.singleton_class.ancestors.include?(BananaResourceNames::DirReads)

# Supervisor readiness signal: a game script has completed a Graphics.update.
# This does not assert that the game has reached its title/menu.
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
