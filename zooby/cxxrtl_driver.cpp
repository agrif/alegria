#include <stdio.h>
#include <getopt.h>

#include <cxxrtl/capi/cxxrtl_capi_vcd.h>

#include <cxxrtl/capi/cxxrtl_capi.cc>
#include <cxxrtl/capi/cxxrtl_capi_vcd.cc>

static const char* short_options = "hc:v:";
static struct option long_options[] = {
    {"help", no_argument, NULL, 'h'},
    {"cycles", required_argument, NULL, 'c'},
    {"vcd", required_argument, NULL, 'v'},
    {0}
};

void print_help(const char* argv0) {
    fprintf(stderr, "USAGE: %s [options]\n\n", argv0);
    for (size_t i = 0; long_options[i].name; i++) {
        const char* long_name = long_options[i].name;
        char c = long_options[i].val;
        if (c && (long_options[i].flag != NULL || strchr(short_options, c) == NULL)) {
            c = 0;
        }

        if (c) {
            fprintf(stderr, "    --%s/-%c", long_name, c);
        } else {
            fprintf(stderr, "    --%s", long_name);
        }

        switch (long_options[i].has_arg) {
        case required_argument:
            fprintf(stderr, " <ARG>");
            break;
        case optional_argument:
            fprintf(stderr, " [ARG]");
            break;
        }

        fprintf(stderr, "\n");
    }
    fprintf(stderr, "\n");
}

int main(int argc, char *const *argv) {
    bool bad_option = false;
    bool help = false;
    char* parse_end = NULL;

    const char* vcd_file_name = NULL;
    size_t max_cycles = 0;

    while (true) {
        int option_index = 0;
        int c = getopt_long(argc, argv, short_options, long_options, &option_index);

        if (c == -1)
            break;

        switch (c) {
        case 'h':
            help = true;
            break;
        case 'c':
            max_cycles = strtol(optarg, &parse_end, 10);
            if (parse_end[0]) {
                bad_option = true;
                fprintf(stderr, "%s: bad cycle count '%s'\n", argv[0], optarg);
            }
            break;
        case 'v':
            vcd_file_name = optarg;
            break;
        case '?':
            bad_option = true;
            break;
        default:
            fprintf(stderr, "%s: unhandled option\n", argv[0]);
            return 1;
        }
    }

    if (optind < argc) {
        bad_option = true;
        for (; optind < argc; optind++) {
            fprintf(stderr, "%s: unexpected argument '%s'\n", argv[0], argv[optind]);
        }
    }

    if (bad_option || help) {
        print_help(argv[0]);
        return bad_option;
    }

    cxxrtl_toplevel design = cxxrtl_design_create();
    cxxrtl_handle top = cxxrtl_create(design);

    cxxrtl_vcd vcd = NULL;
    FILE* vcd_file = NULL;
    const char* vcd_data = NULL;
    size_t vcd_size = 0;
    if (vcd_file_name) {
        if (max_cycles == 0) {
            fprintf(stderr, "%s: stubbornly refusing to record VCD without --cycles\n", argv[0]);
            return 1;
        }

        vcd = cxxrtl_vcd_create();
        cxxrtl_vcd_timescale(vcd, 100, "ns");
        cxxrtl_vcd_add_from_without_memories(vcd, top);

        vcd_file = fopen("test.vcd", "w");
        if (!vcd_file) {
            fprintf(stderr, "%s: could not open file '%s'\n", argv[0], vcd_file_name);
            return 1;
        }
    }

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

    rst->next[0] = 0;
    for (size_t cycle = 0; max_cycles == 0 || cycle < max_cycles; cycle++) {
        clk->next[0] = 0;
        cxxrtl_step(top);

        if (vcd) {
            cxxrtl_vcd_sample(vcd, cycle * 2);
            do {
                cxxrtl_vcd_read(vcd, &vcd_data, &vcd_size);
                fwrite(vcd_data, 1, vcd_size, vcd_file);
            } while (vcd_size > 0);
        }

        clk->next[0] = 1;
        cxxrtl_step(top);

        if (vcd) {
            cxxrtl_vcd_sample(vcd, cycle * 2 + 1);
            do {
                cxxrtl_vcd_read(vcd, &vcd_data, &vcd_size);
                fwrite(vcd_data, 1, vcd_size, vcd_file);
            } while (vcd_size > 0);
        }
    }

    if (vcd) {
        fclose(vcd_file);
        cxxrtl_vcd_destroy(vcd);
    }
    cxxrtl_destroy(top);
}
