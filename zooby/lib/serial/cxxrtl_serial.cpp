#include <iostream>

namespace cxxrtl_design {

    template<size_t BITS>
    struct cxxrtl_serial_tx_stdout : public bb_p_cxxrtl__serial__tx<BITS> {
        bool eval(performer *performer) override {
            if (this->posedge_p_clk()) {
                this->p_ready.next.data[0] = 0x1;
                if (this->p_valid.data[0]) {
                    unsigned char c = this->p_data.data[0] & 0xff;
                    std::cout << c;
                    std::cout.flush();
                }
            }
            return bb_p_cxxrtl__serial__tx<BITS>::eval(performer);
        }
    };

    template<>
    std::unique_ptr<bb_p_cxxrtl__serial__tx<8>>
    bb_p_cxxrtl__serial__tx<8>::create(std::string name, cxxrtl::metadata_map parameters, cxxrtl::metadata_map attributes) {
        return std::make_unique<cxxrtl_serial_tx_stdout<8>>();
    }

}
