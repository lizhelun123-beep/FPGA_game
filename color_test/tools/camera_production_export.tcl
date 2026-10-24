# Export only the checkpoint admitted by the declared-model routed gate.
# No synthesis, implementation or board access; include_bit is invoked once.
set audit [file join $root tools camera_production_audit.py]
exec python -I $audit export_inputs $build_index
set destination [file join $out export]
if {[file exists $destination]} {error "Preserve prior export;no automatic bitgen repeat"}
file mkdir $destination
open_project [file join $root color_test.xpr]
set routed_stage [expr {$build_index >= 3 ? "route" : "declared_model_replay_endpoints"}]
open_checkpoint [file join $out $routed_stage routed.dcp]
if {[get_property PART [current_design]] ne "xc7z020clg400-2"} {error "Wrong export part"}
if {![get_property BITSTREAM.GENERAL.COMPRESS [current_design]]} {error "Unexpected BIT compression identity"}
set mmcm [get_cells system_i/axi_dynclk_0/U0/Inst_mmcme2_drp/mmcm_adv_inst]
if {[llength $mmcm] != 1 || [get_property CLKFBOUT_MULT_F $mmcm] != 10.0 ||
    [get_property DIVCLK_DIVIDE $mmcm] != 1 || [get_property CLKOUT0_DIVIDE_F $mmcm] != 2.0} {error "Export view is not startup"}
# Match the checkpoint's platform to canonical HWH before consuming BIT quota.
write_hw_platform -fixed [file join $destination system_pre_bit.xsa]
exec python -I $audit platform_admission $build_index
exec python -I $audit claim_export $build_index
write_hw_platform -fixed -include_bit [file join $destination system.xsa]
exec python -I $audit export_result $build_index
close_project
puts "CAMERA_PAIRED_ARTIFACT_EXPORT_COMPLETE_NO_BOARD_OPERATIONS"
