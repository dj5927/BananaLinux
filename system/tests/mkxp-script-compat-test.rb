# encoding: UTF-8
# Synthetic game script fixtures, not code from any distributed game.
# mog_anti_lag
class BananaQAVisibility < Sprite
  def test
    @character=Struct.new(:can_update).new(1)
    self.visible = @character.can_update
  end
end
# Galv_Map_Popups
class BananaQAPopup
  def initialize
    @bitmap=Bitmap.new(20,20)
  end
  def test
    if @bitmap.font.respond_to?(:shadow=)
      @bitmap.font.shadow = 1
    end
  end
  def dispose
    @bitmap.dispose
  end
end
# CAO_SP (cacao service pack) 2012.10.04
def convert_escape_characters(text)
  result = text.to_s.clone
  result << "!"
  result
end
if ENV['BANANA_MKXP_SCRIPT_PATCHES']!='off'
  s=BananaQAVisibility.new
  s.test
  raise 'visible' unless s.visible
  s.dispose
  p=BananaQAPopup.new
  p.test
  p.dispose
  raise 'frozen text' unless convert_escape_characters('QA'.freeze)=='QA!'
  raise 'script not patched' unless $RGSS_SCRIPTS[0][3].include?('!!@character.can_update')
else
  raise 'off failed' if $RGSS_SCRIPTS[0][3].include?('self.visible = ' + '!!@character.can_update')
end
f=Font.new
[:bold,:italic,:shadow,:outline].each do |attr|
  w=(attr.to_s+'=').to_sym
  d=("default_"+attr.to_s+"=").to_sym
  dr=("default_"+attr.to_s).to_sym
  if f.respond_to?(w) && f.respond_to?(attr)
    f.send(w,true)
    raise "font #{attr} not disabled" if ENV['BANANA_MKXP_FONT_EFFECTS']=='lightweight' && f.send(attr)
    raise "original font #{attr} disabled" if ENV['BANANA_MKXP_FONT_EFFECTS']!='lightweight' && !f.send(attr)
  end
  if Font.respond_to?(d) && Font.respond_to?(dr)
    Font.send(d,true)
    raise "default font #{attr} not disabled" if ENV['BANANA_MKXP_FONT_EFFECTS']=='lightweight' && Font.send(dr)
  end
end
puts "QA COMPAT PASS #{RUBY_VERSION} patches=#{ENV['BANANA_MKXP_SCRIPT_PATCHES']} fonts=#{ENV['BANANA_MKXP_FONT_EFFECTS']}"
Graphics.update
puts 'QA FRAME PASS'
exit
