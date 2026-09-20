/* SPDX-License-Identifier: GPL-2.0-only
 * Host scaffolding for the frozen upstream standard-mode oracle.
 * uint64_t models the target's unsigned long (host Windows uses LLP64). */
#include <stdint.h>
#define WARN_ON(x) (x)
#define I2C_MAX_FAST_MODE_PLUS_FREQ 1000000u
#define DIV_ROUND_UP(n,d) (((n)+(d)-1)/(d))
#define DATA_UPDATE_POINT 3u
#define START_SETUP_MAX 3u
#define STOP_SETUP_MAX 3u
#define REG_CON_SDA_CFG(x) ((x)<<8)
#define REG_CON_STA_CFG(x) ((x)<<12)
#define REG_CON_STO_CFG(x) ((x)<<14)
struct i2c_timings {uint32_t bus_freq_hz,scl_rise_ns,scl_fall_ns;};
struct rk3x_i2c_calced_timings {uint64_t div_low,div_high;unsigned int tuning;};
struct i2c_spec_values {uint64_t min_low_ns,min_high_ns,min_setup_start_ns,max_data_hold_ns,min_data_setup_ns,min_setup_stop_ns;};
static const struct i2c_spec_values *rk3x_i2c_get_spec(unsigned int speed){
 static const struct i2c_spec_values standard={4700,4000,4700,3450,250,4000};
 (void)speed;return &standard;
}
