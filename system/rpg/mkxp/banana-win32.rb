# encoding: UTF-8
# BananaOS handheld adaptation of the RPG-Maker-Player Win32 wrapper
# (Ancurio 2014, Splendide Imaginarius 2023-2024, CC0).
# Never change the KMS mode or inject host keyboard events.
module BananaWin32
  @logged = {}
  def self.note(dll, fn)
    key = dll + ':' + fn
    return if @logged[key]
    @logged[key] = true
    warn("[Win32API] unsupported #{key}; returning 0")
  end
  def self.write(buf, data)
    return false unless buf.is_a?(String)
    limit=buf.respond_to?(:bytesize) ? buf.bytesize : buf.size
    i=0
    data.each_byte do |b|
      break if i>=limit
      if buf.respond_to?(:setbyte)
        buf.setbyte(i,b)
      else
        buf[i]=b
      end
      i+=1
    end
    true
  end
  def self.dimension(axis)
    m = axis==0 ? :display_width : :display_height
    n = Graphics.respond_to?(m) ? Graphics.send(m) : 0
    n.to_i>0 ? n : (axis==0 ? Graphics.width : Graphics.height)
  end
  PAD = {0x25=>:LEFT,0x26=>:UP,0x27=>:RIGHT,0x28=>:DOWN,0x0d=>:C,0x1b=>:B,0x20=>:C}
  SCAN = {0x25=>80,0x26=>82,0x27=>79,0x28=>81,0x0d=>40,0x1b=>41,0x20=>44,0x08=>42,0x09=>43}
  def self.active(value)
    value && value!=0
  end
  def self.pressed(vk, states=nil, buttons=nil, axes=nil)
    scan=SCAN[vk]
    scan=vk-65+4 if vk>=65 && vk<=90
    scan=vk-0x70+58 if vk>=0x70 && vk<=0x7b
    states ||= Input.respond_to?(:raw_key_states) ? Input.raw_key_states : []
    val=scan && states[scan]
    return true if active(val)
    if vk==0x10 || vk==0x11 || vk==0x12
      sc={0x10=>[225,229],0x11=>[224,228],0x12=>[226,230]}[vk]
      return true if sc.any?{|i| active(states[i])}
    end
    key=PAD[vk]
    # Reference mapping for Eternal Senia only; not global game remapping.
    if ENV['BANANA_MKXP_SENIA']=='1'
      if Input.const_defined?('Controller')
        controller=Input.const_get('Controller')
        buttons ||= controller.respond_to?(:raw_button_states) ? controller.raw_button_states : []
        axes ||= controller.respond_to?(:raw_axes) ? controller.raw_axes : []
        # SDL controller indices: X=2, right shoulder=10, right trigger axis=5.
        return true if vk==0x43 && active(buttons[2])
        return true if vk==0x45 && active(buttons[10])
        return true if vk==0x52 && axes[5].to_f>0.5
      end
      key={0x43=>:A,0x45=>:R}[vk] || key
    end
    return false unless key
    key=Input.const_get(key.to_s) if Input.const_defined?(key.to_s)
    !!Input.press?(key)
  rescue StandardError
    false
  end
  def self.invoke(dll, fn, a)
    f=fn.downcase
    case dll
    when 'user32'
      case f
      when 'getsystemmetrics'
        return dimension(a[0].to_i) if [0,1].include?(a[0].to_i)
        return 0
      when 'getwindowrect','getclientrect'
        return write(a[1],[0,0,Graphics.width,Graphics.height].pack('l4')) ? 1 : 0
      when 'findwindow','findwindowa','findwindoww','findwindowex','findwindowexa','findwindowexw','getforegroundwindow','getactivewindow','getdesktopwindow','getdc'
        return 42
      when 'setwindowlong','setwindowlonga','setwindowlongw','setwindowlongptr','setwindowlongptra','setwindowlongptrw','getwindowlong','getwindowlonga','getwindowlongw'
        return 0
      when 'setwindowpos','movewindow','showwindow','updatewindow','setforegroundwindow','releasedc','fillrect','screentoclient','clienttoscreen','iswindow','iswindowvisible','adjustwindowrect','adjustwindowrectex','setcursorpos'
        return 1
      when 'keybd_event','showcursor','setcursor','changedisplaysettings','changedisplaysettingsa','changedisplaysettingsw'
        return 0
      when 'systemparametersinfo','systemparametersinfoa','systemparametersinfow'
        return write(a[2],[0,0,dimension(0),dimension(1)].pack('l4')) ? 1 : 0 if a[0].to_i==0x30
        return 0
      when 'getasynckeystate','getkeystate'
        return pressed(a[0].to_i) ? 0x8000 : 0
      when 'getkeyboardstate'
        states=Input.respond_to?(:raw_key_states) ? Input.raw_key_states : []
        controller=Input.const_defined?('Controller') ? Input.const_get('Controller') : nil
        buttons=controller && controller.respond_to?(:raw_button_states) ? controller.raw_button_states : []
        axes=controller && controller.respond_to?(:raw_axes) ? controller.raw_axes : []
        return write(a[0],(0..255).map{|vk| pressed(vk,states,buttons,axes) ? 128 : 0}.pack('C*')) ? 1 : 0
      when 'getcursorpos'
        return write(a[0],[Input.respond_to?(:mouse_x) ? Input.mouse_x : 0,Input.respond_to?(:mouse_y) ? Input.mouse_y : 0].pack('l2')) ? 1 : 0
      when 'getwindowtextlength','getwindowtextlengtha'
        return 11
      when 'getwindowtext','getwindowtexta'
        s='RGSS Player'[0,[a[2].to_i-1,0].max]
        return write(a[1],s+"\0") ? s.size : 0
      end
    when 'kernel32'
      case f
      when 'gettickcount','gettickcount64','timegettime'
        return ((Time.now.to_f*1000).to_i & 0xffffffff)
      when 'getcurrentprocessid'
        return Process.pid
      when 'rtlzeromemory'
        return 0 unless a[0].is_a?(String)
        write(a[0],"\0"*[[a[1].to_i,a[0].size,0x100000].min,0].max)
        return 0
      when 'getprivateprofilestring','getprivateprofilestringa'
        section,key,default,buf,size,path=a
        value=default.to_s
        begin
          current=nil
          File.foreach(path.to_s.tr('\\','/')) do |line|
            if line.strip =~ /^\[(.*)\]$/
              current=$1
            elsif current==section && line =~ /^([^=]+)=(.*)$/ && $1.strip==key
              value=$2.strip; break
            end
          end
        rescue StandardError
        end
        value=value[0,[size.to_i-1,0].max]
        return write(buf,value+"\0") ? value.size : 0
      end
    when 'gdi32'
      return 1 if ['createsolidbrush','deleteobject'].include?(f)
    when 'winmm'
      return (Time.now.to_f*1000).to_i & 0xffffffff if f=='timegettime'
    end
    note(dll,fn)
    0
  end
end
if defined?(Win32API)
  class Win32API
    unless method_defined?(:banana_native_call)
      alias_method :banana_native_initialize,:initialize
      alias_method :banana_native_call,:call
      def initialize(dll,fn,*args)
        name=dll.to_s.tr('\\','/').split('/')[-1].to_s.downcase.sub(/\.dll$/,'')
        if ['user32','kernel32','gdi32','winmm'].include?(name)
          @banana_dll=name; @banana_fn=fn.to_s
        else
          banana_native_initialize(dll,fn,*args)
        end
      end
      def call(*args)
        return banana_native_call(*args) unless @banana_dll
        BananaWin32.invoke(@banana_dll,@banana_fn,args)
      end
      alias_method :Call,:call
    end
  end
  puts '[MKXP] Banana Win32 compatibility loaded'
end
