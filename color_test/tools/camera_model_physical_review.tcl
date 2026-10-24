# Verify repaired production model entry and physical equivalence on the same
# existing routed design. No synth/opt/place/route/export or board operations.
set root [file normalize [file join [file dirname [info script]] ..]]
set build [file join $root build pl_rate93_production build_2]
set out [file join $build model_physical_review]
set original_dump 1
if {$argc == 1 && [lindex $argv 0] eq "--flat-context-correction"} {
    set f [open [file join $build model_physical_review.log] r];set prior [read $f];close $f
    if {[string first "Unexpected obsolete window outside known IP constraints" $prior]<0} {error "Unexpected prior preparation failure"}
    set out [file join $build model_physical_review_flat]
    set original_dump 0
} elseif {$argc != 0} {error "Unknown physical review invocation"}
if {[file exists $out]} {error "One physical/model review only"}
file mkdir $out
proc dump_hardware {out label} {
    file mkdir [file join $out $label]
    write_edif [file join $out $label design.edf]
    set f [open [file join $out ${label}_placement.tsv] w]
    foreach cell [lsort [get_cells -hier -filter {IS_PRIMITIVE == 1}]] {
        puts $f "$cell\t[get_property REF_NAME $cell]\t[get_property LOC $cell]\t[get_property BEL $cell]"
    }
    close $f
    set f [open [file join $out ${label}_routes.tsv] w]
    foreach net [lsort [get_nets -hier]] {puts $f "$net\t[get_property ROUTE $net]"}
    close $f
}
open_checkpoint [file join $build route routed.dcp]
if {$original_dump} {dump_hardware $out original}
source [file join $root tools camera_input_model.tcl]
camera_apply_declared_input_model $root $out
dump_hardware $out repaired_entry
close_design
open_checkpoint [file join $build declared_model_replay_endpoints routed.dcp]
dump_hardware $out accepted_checkpoint
close_design
puts "CAMERA_MODEL_ENTRY_AND_PHYSICAL_INVENTORIES_COMPLETE_NO_BUILD_EXPORT"
