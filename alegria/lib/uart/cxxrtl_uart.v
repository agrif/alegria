(* cxxrtl_blackbox, cxxrtl_template = "MAX_BITS" *)
module cxxrtl_uart_rx(...);
    parameter MAX_BITS = 8;
    (* cxxrtl_edge = "p" *) input clk;
    input rst;
    (* cxxrtl_sync, cxxrtl_width = "MAX_BITS" *) output [MAX_BITS-1:0] data;
    (* cxxrtl_sync *) output valid;
    input ready;
    input rts;
endmodule

(* cxxrtl_blackbox, cxxrtl_template = "MAX_BITS" *)
module cxxrtl_uart_tx(...);
    parameter MAX_BITS = 8;
    (* cxxrtl_edge = "p" *) input clk;
    input rst;
    (* cxxrtl_width = "MAX_BITS" *) input [MAX_BITS-1:0] data;
    input valid;
    (* cxxrtl_sync *) output ready;
endmodule
