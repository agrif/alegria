#include <iostream>
#include <fcntl.h>
#include <stdio.h>
#include <termios.h>
#include <unistd.h>

namespace cxxrtl_design {

    template<size_t BITS>
    struct cxxrtl_serial_rx_stdin : public bb_p_cxxrtl__serial__rx<BITS> {
        int fd;
        cxxrtl_serial_rx_stdin() : bb_p_cxxrtl__serial__rx<BITS>() {
            fd = fileno(stdin);
            int flags = fcntl(fd, F_GETFL, 0);

            // nonblocking
            fcntl(fd, F_SETFL, flags | O_NONBLOCK);

            struct termios old_tio, new_tio;
            tcgetattr(fd, &old_tio);
            new_tio = old_tio;

            // turn off canonical mode and echo
            new_tio.c_lflag &= ~ICANON & ~ECHO;

            // turn \n into \r
            new_tio.c_iflag &= INLCR;

            // minimum input characters and timeout
            new_tio.c_cc[VMIN] = 0;
            new_tio.c_cc[VTIME] = 0;

            tcsetattr(fd, TCSANOW, &new_tio);

            // TODO: at exit:
            // tcsetattr(fd, TCSANOW, &old_tio);
            // fcntl(fd, F_SETFL, flags);
        }

        bool eval(performer *performer) override {
            if (this->posedge_p_clk()) {
                // check for transfer out and execute
                if (this->p_ready.data[0] && this->p_valid.curr.data[0]) {
                    this->p_valid.next.data[0] = 0;
                }

                // check for new character if next cycle is open
                if (!this->p_valid.next.data[0] && this->p_rts.data[0]) {
                    char c;
                    ssize_t bytes_read = read(fd, &c, 1);
                    if (bytes_read > 0) {
                        this->p_data.next.data[0] = c;
                        this->p_valid.next.data[0] = 1;
                    } else if (bytes_read < 0) {
                        if (errno != EWOULDBLOCK && errno != EAGAIN) {
                            // this is a real error
                            std::cerr << "read error" << std::endl;
                            abort();
                        }
                    }
                }
            }

            return bb_p_cxxrtl__serial__rx<BITS>::eval(performer);
        }
    };

    template<>
    std::unique_ptr<bb_p_cxxrtl__serial__rx<8>>
    bb_p_cxxrtl__serial__rx<8>::create(std::string name, cxxrtl::metadata_map parameters, cxxrtl::metadata_map attributes) {
        return std::make_unique<cxxrtl_serial_rx_stdin<8>>();
    }

    template<size_t BITS>
    struct cxxrtl_serial_tx_stdout : public bb_p_cxxrtl__serial__tx<BITS> {
        bool eval(performer *performer) override {
            if (this->posedge_p_clk()) {
                // always ready
                this->p_ready.next.data[0] = 0x1;

                // check if output is present and execute
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
