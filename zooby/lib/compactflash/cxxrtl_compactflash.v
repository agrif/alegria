(* cxxrtl_blackbox *)
module cxxrtl_compactflash(...);
    (* cxxrtl_edge = "p" *) input clk;
    (* cxxrtl_sync *) output [7:0] data_rd;
    (* cxxrtl_sync *) output data_rd_valid;
    input [7:0] data_wr;
    input [10:0] addr;
    input cs0_n;
    input cs1_n;
    input iord_n;
    input iowr_n;
    input reset_n;
    (* cxxrtl_sync *) output dasp_n;
endmodule
