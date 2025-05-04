(* cxxrtl_blackbox, cxxrtl_template = "BITS" *)
module cxxrtl_serial_tx(...);
    parameter BITS = 8;
    (* cxxrtl_edge = "p" *) input clk;
    (* cxxrtl_width = "BITS" *) input [BITS-1:0] data;
    input valid;
    (* cxxrtl_sync *) output ready;
endmodule
