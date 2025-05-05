(* cxxrtl_blackbox, cxxrtl_template = "BITS" *)
module cxxrtl_serial_rx(...);
    parameter BITS = 8;
    (* cxxrtl_edge = "p" *) input clk;
    (* cxxrtl_sync, cxxrtl_width = "BITS" *) output [BITS-1:0] data;
    (* cxxrtl_sync *) output valid;
    input ready;
    input rts;
endmodule

(* cxxrtl_blackbox, cxxrtl_template = "BITS" *)
module cxxrtl_serial_tx(...);
    parameter BITS = 8;
    (* cxxrtl_edge = "p" *) input clk;
    (* cxxrtl_width = "BITS" *) input [BITS-1:0] data;
    input valid;
    (* cxxrtl_sync *) output ready;
endmodule
