#include <iostream>

#define SECTOR_SIZE 512

namespace cxxrtl_design {

    struct cxxrtl_compactflash_emu : public bb_p_cxxrtl__compactflash {
        uint8_t count;
        uint8_t sector;
        uint16_t cylinder;
        uint8_t head;
        bool device_select;
        uint8_t mode;
        uint8_t feature;

        uint16_t read_sector_count;
        uint8_t read_buffer[SECTOR_SIZE];
        size_t read_buffer_next;

        cxxrtl_compactflash_emu() : bb_p_cxxrtl__compactflash() {
            count = 0;
            sector = 1;
            cylinder = 0;
            head = 0;
            device_select = false;
            feature = 0;
            mode = 0b101; // 0b101 is CHS, 0b111 is LBA28

            read_sector_count = 0;
            read_buffer_next = SECTOR_SIZE;
        }

        uint8_t read_reg(uint8_t addr) {
            switch (addr) {
            case 0x0:
                // data
                if (read_buffer_next < SECTOR_SIZE) {
                    std::cerr << "CF read " << std::hex << read_buffer_next << std::endl;
                    uint8_t data = read_buffer[read_buffer_next];
                    read_buffer_next++;

                    if (read_buffer_next >= SECTOR_SIZE) {
                        read_sector_count--;
                        if (read_sector_count) {
                            std::cerr << "CF read end, " << std::hex << read_sector_count << " remain" << std::endl;
                            // FIXME read a new chunk
                            read_buffer_next = 0;
                        }
                    }

                    return data;
                }
                return 0;
            case 0x1:
                // error
                return 0;
            case 0x2:
                // count
                return count;
            case 0x3:
                // sector, starts at 1
                return sector;
            case 0x4:
                // cylinder bits 0..7
                return cylinder & 0xff;
            case 0x5:
                // cylinder bits 15..8 (only 2 bits unless LBA)
                return (cylinder >> 8) & 0xff;
            case 0x6:
                // head and device select
                return ((mode & 0x3) << 5) | (device_select << 4) | (head & 0xf);
            case 0x7:
                // status register
                // 0: error
                // 1: index pulse
                // 2: ecc bit
                // 3: drq, data pending (in or out)
                // 4: skc, seek success
                // 5: wft, write error
                // 6: rdy, disk finished power-up
                // 7: bsy, disk is doing something
                return (1 << 6)
                    | ((read_buffer_next < SECTOR_SIZE) << 3);
            default:
                return 0;
            }
        }

        void write_reg(uint8_t addr, uint8_t val) {
            switch (addr) {
            case 0x0:
                // data
                break;
            case 0x1:
                // feature
                feature = val;
                break;
            case 0x2:
                // count
                count = val;
                break;
            case 0x3:
                // sector, starts at 1
                sector = val;
                break;
            case 0x4:
                // cylinder bits 0..7
                cylinder &= 0xff00;
                cylinder |= val;
                break;
            case 0x5:
                // cylinder bits 15..8 (only 2 bits unless LBA)
                cylinder &= 0x00ff;
                cylinder |= val << 8;
                break;
            case 0x6:
                // head, device, mode select
                mode = val >> 5;
                device_select = (val >> 4) & 0x1;
                head = val & 0xf;
                break;
            case 0x7:
                // command register
                do_command(val);
                break;
            }
        }

        void do_command(uint8_t cmd) {
            switch (cmd) {
            case 0x20:
                // read sectors
                do_read();
                break;
            case 0xef:
                // set features
                switch (feature) {
                case 0x01:
                    // enable 8-bit transfer
                    break;
                case 0x02:
                    // enable volatile write cache
                    break;
                case 0x82:
                    // disable volatile write cache
                    break;
                default:
                    std::cerr << "CF unknown set features " << std::hex << (int)feature << std::endl;
                }
                break;
            default:
                std::cerr << "CF unknown command " << std::hex << (int)cmd << std::endl;
            }
        }

        void do_read() {
            uint16_t real_count = count;
            if (!count) {
                real_count = 0x100;
            }
            std::cerr << "CF read " << std::bitset<3>(mode) << " (" << device_select << ") from " << std::hex << cylinder << " " << (int)head << " " << (int)sector << " for " << real_count << std::endl;

            for (size_t i = 0; i < SECTOR_SIZE; i++) {
                read_buffer[i] = i;
            }
            read_buffer_next = 0;
            read_sector_count = real_count;
        }

        bool eval(performer *performer) override {
            if (posedge_p_clk()) {
                if (!p_cs0__n && !p_iord__n) {
                    if (!p_data__rd__valid.get<bool>()) {
                        p_data__rd.next.data[0] = read_reg(p_addr.get<uint16_t>());
                    }
                    p_data__rd__valid.next.data[0] = 1;
                } else {
                    p_data__rd.next.data[0] = 0;
                    p_data__rd__valid.next.data[0] = 0;
                }

                if (!p_cs0__n && !p_iowr__n) {
                    write_reg(p_addr.get<uint16_t>(), p_data__wr.get<uint8_t>());
                }
            }

            return bb_p_cxxrtl__compactflash::eval(performer);
        }
    };

    std::unique_ptr<bb_p_cxxrtl__compactflash>
    bb_p_cxxrtl__compactflash::create(std::string name, cxxrtl::metadata_map parameters, cxxrtl::metadata_map attributes) {
        return std::make_unique<cxxrtl_compactflash_emu>();
    }
}
