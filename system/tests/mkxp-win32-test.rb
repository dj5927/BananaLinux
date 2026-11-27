# encoding: UTF-8
# Real RGSS fixture; exercises the Windows fullscreen script API family.
metric=Win32API.new('user32','GetSystemMetrics','i','i')
raise 'metrics' unless metric.call(0)>0 && metric.Call(1)>0
find=Win32API.new('USER32.DLL','FindWindowA','pp','l')
hwnd=find.call('RGSS Player',nil)
raise 'window' unless hwnd!=0
rect="\0"*16
raise 'rect' unless Win32API.new('user32','GetClientRect','lp','i').call(hwnd,rect)==1
raise 'dimensions' unless rect.unpack('l4')==[0,0,Graphics.width,Graphics.height]
pos=Win32API.new('user32','SetWindowPos','lllllll','i')
raise 'position' unless pos.call(hwnd,0,0,0,800,600,0)==1
raise 'screen altered' unless rect.unpack('l4')==[0,0,Graphics.width,Graphics.height]
raise 'keyboard' unless [0,0x8000].include?(Win32API.new('user32','GetAsyncKeyState','i','i').call(0x43))
states="\0"*256
raise 'keyboard buffer' unless Win32API.new('user32','GetKeyboardState','p','i').call(states)==1
if Input.const_defined?('Controller')
  buttons=Array.new(16,false); axes=Array.new(6,0.0); keys=Array.new(256,false)
  buttons[2]=true; buttons[10]=true; axes[5]=0.9
  raise 'Senia X/R1/R2 mapping' unless [0x43,0x45,0x52].all?{|vk| BananaWin32.pressed(vk,keys,buttons,axes)}
end
raise 'unknown API' unless Win32API.new('user32','NotImplementedFixture','','i').call==0
puts "QA WIN32 PASS #{RUBY_VERSION}"
Graphics.update
puts 'QA FRAME PASS'
exit
