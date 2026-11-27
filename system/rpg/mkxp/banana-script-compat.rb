# encoding: UTF-8
# Narrow, in-memory compatibility rules inspired by the documented fixes in
# Kawariki mkxp/patches.rb (bb5ea9a) and rpgmakermlinux-cicpoffs
# Kawariki-patches/patches.rb (5af2721). No third-party port scripts copied.
# Compatible with Ruby 1.8 through 3.x; never remove whole game scripts.
module BananaScriptCompat
  def self.patch_scripts
    return unless defined?($RGSS_SCRIPTS) && $RGSS_SCRIPTS.is_a?(Array)
    total=0
    $RGSS_SCRIPTS.each_with_index do |section,index|
      next unless section.is_a?(Array) && section[3].is_a?(String)
      begin
        src=section[3]
        patched=src.dup
        rules=[]
        if src.include?('mog_anti_lag')
          n=patched.gsub!(/^([ \t]*)self\.visible = @character\.can_update(?=[ \t]*(?:#|$))/, '\\1self.visible = !!@character.can_update')
          rules << 'MOG visible boolean' if n
        end
        if src.include?('Galv_Map_Popups')
          n=patched.gsub!(/^([ \t]*[\w@.$]+\.font\.shadow[ \t]*=[ \t]*)([01])(?=[ \t]*(?:#|$))/) {|match| $1+($2=='0' ? 'false' : 'true')}
          rules << 'Galv font shadow boolean' if n
        end
        if src.include?('CAO_SP (cacao service pack) 2012.10.04') && src.include?('def convert_escape_characters(text)')
          n=patched.gsub!(/^([ \t]*)result = text\.to_s\.clone(?=[ \t]*(?:#|$))/, '\\1result = text.to_s.dup')
          rules << 'CAO mutable text copy' if n
        end
        if !rules.empty?
          section[3]=patched
          total+=rules.size
          puts "[MKXP compat] section=#{index} rules=#{rules.join(', ')}"
        end
      rescue StandardError => e
        warn("[MKXP compat] section=#{index} skipped: #{e.class}: #{e.message}")
      end
    end
    puts "[MKXP compat] Applied #{total} targeted fixes"
  end
  def self.disable_writer(klass, writer)
    return unless klass.method_defined?(writer)
    original=("banana_original_"+writer.to_s).to_sym
    return if klass.method_defined?(original)
    klass.class_eval do
      alias_method original,writer
      define_method(writer) {|value| send(original,false)}
    end
  end
  def self.light_fonts
    return unless defined?(Font)
    singleton=class << Font; self; end
    [:bold,:italic,:shadow,:outline].each do |attr|
      writer=(attr.to_s+"=").to_sym
      default_writer=("default_"+attr.to_s+"=").to_sym
      disable_writer(Font,writer)
      disable_writer(singleton,default_writer)
      Font.send(default_writer,false) if Font.respond_to?(default_writer)
    end
    puts '[MKXP compat] Lightweight font effects enabled'
  end
end
BananaScriptCompat.patch_scripts unless ENV['BANANA_MKXP_SCRIPT_PATCHES']=='off'
BananaScriptCompat.light_fonts if ENV['BANANA_MKXP_FONT_EFFECTS']=='lightweight'
