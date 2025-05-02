#include <stdio.h>

#include <cxxrtl/capi/cxxrtl_capi_vcd.h>

#include <cxxrtl/capi/cxxrtl_capi.cc>
#include <cxxrtl/capi/cxxrtl_capi_vcd.cc>

int main() {
    cxxrtl_toplevel design = cxxrtl_design_create();
    cxxrtl_handle top = cxxrtl_create(design);

    cxxrtl_vcd vcd = cxxrtl_vcd_create();
    cxxrtl_vcd_timescale(vcd, 100, "ns");
    cxxrtl_vcd_add_from_without_memories(vcd, top);

    // clk and rst names are a bit funny
    // "clk" and "rst" work but have no next field
    cxxrtl_object *clk = cxxrtl_get(top, "clk_0__io");
    cxxrtl_object *rst = cxxrtl_get(top, "rst_0__io");

    if (!clk || !rst) {
        return 1;
    }

    rst->next[0] = 1;
    for (int reset_cycle = 0; reset_cycle < 20; reset_cycle++) {
        clk->next[0] = 0;
        cxxrtl_step(top);

        clk->next[0] = 1;
        cxxrtl_step(top);
    }

    FILE* vcd_file = fopen("test.vcd", "w");
    if (!vcd_file) {
        return 1;
    }

    const char* data = NULL;
    size_t size = 0;

    rst->next[0] = 0;
    for (int cycle = 0; cycle < 10000; cycle++) {
        clk->next[0] = 0;
        cxxrtl_step(top);
        cxxrtl_vcd_sample(vcd, cycle * 2);

        do {
            cxxrtl_vcd_read(vcd, &data, &size);
            fwrite(data, 1, size, vcd_file);
        } while (size > 0);

        clk->next[0] = 1;
        cxxrtl_step(top);
        cxxrtl_vcd_sample(vcd, cycle * 2 + 1);

        do {
            cxxrtl_vcd_read(vcd, &data, &size);
            fwrite(data, 1, size, vcd_file);
        } while (size > 0);
    }

    fclose(vcd_file);
    cxxrtl_vcd_destroy(vcd);
    cxxrtl_destroy(top);
}
