#include "reference-prefix.h"
static int rk3x_i2c_v1_calc_timings(uint64_t clk_rate,
				    struct i2c_timings *t,
				    struct rk3x_i2c_calced_timings *t_calc)
{
	uint64_t min_low_ns, min_high_ns;
	uint64_t min_setup_start_ns, min_setup_data_ns;
	uint64_t min_setup_stop_ns, max_hold_data_ns;

	uint64_t clk_rate_khz, scl_rate_khz;

	uint64_t min_low_div, min_high_div;

	uint64_t min_div_for_hold, min_total_div;
	uint64_t extra_div, extra_low_div;
	uint64_t sda_update_cfg, stp_sta_cfg, stp_sto_cfg;

	const struct i2c_spec_values *spec;
	int ret = 0;

	/* Support standard-mode, fast-mode and fast-mode plus */
	if (WARN_ON(t->bus_freq_hz > I2C_MAX_FAST_MODE_PLUS_FREQ))
		t->bus_freq_hz = I2C_MAX_FAST_MODE_PLUS_FREQ;

	/* prevent scl_rate_khz from becoming 0 */
	if (WARN_ON(t->bus_freq_hz < 1000))
		t->bus_freq_hz = 1000;

	/*
	 * min_low_ns: The minimum number of ns we need to hold low to
	 *	       meet I2C specification, should include fall time.
	 * min_high_ns: The minimum number of ns we need to hold high to
	 *	        meet I2C specification, should include rise time.
	 */
	spec = rk3x_i2c_get_spec(t->bus_freq_hz);

	/* calculate min-divh and min-divl */
	clk_rate_khz = DIV_ROUND_UP(clk_rate, 1000);
	scl_rate_khz = t->bus_freq_hz / 1000;
	min_total_div = DIV_ROUND_UP(clk_rate_khz, scl_rate_khz * 8);

	min_high_ns = t->scl_rise_ns + spec->min_high_ns;
	min_high_div = DIV_ROUND_UP(clk_rate_khz * min_high_ns, 8 * 1000000);

	min_low_ns = t->scl_fall_ns + spec->min_low_ns;
	min_low_div = DIV_ROUND_UP(clk_rate_khz * min_low_ns, 8 * 1000000);

	/*
	 * Final divh and divl must be greater than 0, otherwise the
	 * hardware would not output the i2c clk.
	 */
	min_high_div = (min_high_div < 1) ? 2 : min_high_div;
	min_low_div = (min_low_div < 1) ? 2 : min_low_div;

	/* These are the min dividers needed for min hold times. */
	min_div_for_hold = (min_low_div + min_high_div);

	/*
	 * This is the maximum divider so we don't go over the maximum.
	 * We don't round up here (we round down) since this is a maximum.
	 */
	if (min_div_for_hold >= min_total_div) {
		/*
		 * Time needed to meet hold requirements is important.
		 * Just use that.
		 */
		t_calc->div_low = min_low_div;
		t_calc->div_high = min_high_div;
	} else {
		/*
		 * We've got to distribute some time among the low and high
		 * so we don't run too fast.
		 * We'll try to split things up by the scale of min_low_div and
		 * min_high_div, biasing slightly towards having a higher div
		 * for low (spend more time low).
		 */
		extra_div = min_total_div - min_div_for_hold;
		extra_low_div = DIV_ROUND_UP(min_low_div * extra_div,
					     min_div_for_hold);

		t_calc->div_low = min_low_div + extra_low_div;
		t_calc->div_high = min_high_div + (extra_div - extra_low_div);
	}

	/*
	 * calculate sda data hold count by the rules, data_upd_point = 3
	 * is a appropriate value to reduce calculated times, max is 0x5.
	 */
	for (sda_update_cfg = DATA_UPDATE_POINT; sda_update_cfg > 0; sda_update_cfg--) {
		max_hold_data_ns =  DIV_ROUND_UP((sda_update_cfg
						 * (t_calc->div_low) + 1)
						 * 1000000, clk_rate_khz);
		min_setup_data_ns =  DIV_ROUND_UP(((8 - sda_update_cfg)
						 * (t_calc->div_low) + 1)
						 * 1000000, clk_rate_khz);
		if ((max_hold_data_ns < spec->max_data_hold_ns) &&
		    (min_setup_data_ns > spec->min_data_setup_ns))
			break;
	}
	sda_update_cfg = (sda_update_cfg ? sda_update_cfg : 1) & DATA_UPDATE_POINT;

	/* calculate setup start config, min is over 1 by DIV_ROUND_UP */
	min_setup_start_ns = t->scl_rise_ns + spec->min_setup_start_ns;
	stp_sta_cfg = DIV_ROUND_UP(clk_rate_khz * min_setup_start_ns
			   - 1000000, 8 * 1000000 * (t_calc->div_high));
	stp_sta_cfg = (stp_sta_cfg > START_SETUP_MAX) ? START_SETUP_MAX : stp_sta_cfg;

	/* calculate setup stop config, min is over 1 by DIV_ROUND_UP */
	min_setup_stop_ns = t->scl_rise_ns + spec->min_setup_stop_ns;
	stp_sto_cfg = DIV_ROUND_UP(clk_rate_khz * min_setup_stop_ns
			   - 1000000, 8 * 1000000 * (t_calc->div_high));
	stp_sto_cfg = (stp_sto_cfg > STOP_SETUP_MAX) ? STOP_SETUP_MAX : stp_sto_cfg;

	t_calc->tuning = REG_CON_SDA_CFG(--sda_update_cfg) |
			 REG_CON_STA_CFG(--stp_sta_cfg) |
			 REG_CON_STO_CFG(--stp_sto_cfg);

	t_calc->div_low--;
	t_calc->div_high--;

	/* Maximum divider supported by hw is 0xffff */
	if (t_calc->div_low > 0xffff) {
		t_calc->div_low = 0xffff;
		ret = -EINVAL;
	}

	if (t_calc->div_high > 0xffff) {
		t_calc->div_high = 0xffff;
		ret = -EINVAL;
	}

	return ret;
}
