-- AX7Z020B diagnostic only. Board X2=50 MHz on U18 (PL_GCLK1).
-- Fixed integer MMCMs: 50*20/10=100 MHz; 100*41/5/2=410 MHz;
-- same MMCM CLKOUT0 -> BUFIO(serial) and BUFR/5(pixel=82 MHz).
library ieee;
use ieee.std_logic_1164.all;
library unisim;
use unisim.vcomponents.all;

entity hdmi_colorbars_top is
  port (ref_clk_50 : in std_logic;
        TMDS_clk_p, TMDS_clk_n : out std_logic;
        TMDS_data_p, TMDS_data_n : out std_logic_vector(2 downto 0));
end entity;

architecture rtl of hdmi_colorbars_top is
  signal ref_ibuf, ref50, ref100_raw, ref100 : std_logic;
  signal fb1_raw, fb1, fb2_raw, fb2, serial_raw, serial_clk, pixel_clk : std_logic;
  signal lock1, lock2, reset1, reset2, video_reset, video_hold : std_logic;
  signal rgb : std_logic_vector(23 downto 0);
  signal hs, vs, de : std_logic;
begin
  reference_input : IBUF port map (I => ref_clk_50, O => ref_ibuf);
  reference_global : BUFG port map (I => ref_ibuf, O => ref50);
  reference_guard : entity work.hdmi_colorbars_guard
    port map (ref_clk => ref50, async_hold => '0', locked => lock1, mmcm_reset => reset1);
  double_reference : MMCME2_BASE
    generic map (CLKIN1_PERIOD => 20.0, CLKFBOUT_MULT_F => 20.0,
                 DIVCLK_DIVIDE => 1, CLKOUT0_DIVIDE_F => 10.0, STARTUP_WAIT => false)
    port map (CLKIN1 => ref50, CLKFBIN => fb1, CLKFBOUT => fb1_raw,
      CLKFBOUTB => open, CLKOUT0 => ref100_raw, CLKOUT0B => open,
      CLKOUT1 => open, CLKOUT1B => open, CLKOUT2 => open, CLKOUT2B => open,
      CLKOUT3 => open, CLKOUT3B => open, CLKOUT4 => open, CLKOUT5 => open,
      CLKOUT6 => open, LOCKED => lock1, RST => reset1, PWRDWN => '0');
  feedback1 : BUFG port map (I => fb1_raw, O => fb1);
  reference100_global : BUFG port map (I => ref100_raw, O => ref100);
  video_guard : entity work.hdmi_colorbars_guard
    port map (ref_clk => ref100, async_hold => not lock1, locked => lock2, mmcm_reset => reset2);
  video_mmcm : MMCME2_BASE
    generic map (CLKIN1_PERIOD => 10.0, CLKFBOUT_MULT_F => 41.0,
                 DIVCLK_DIVIDE => 5, CLKOUT0_DIVIDE_F => 2.0, STARTUP_WAIT => false)
    port map (CLKIN1 => ref100, CLKFBIN => fb2, CLKFBOUT => fb2_raw,
      CLKFBOUTB => open, CLKOUT0 => serial_raw, CLKOUT0B => open,
      CLKOUT1 => open, CLKOUT1B => open, CLKOUT2 => open, CLKOUT2B => open,
      CLKOUT3 => open, CLKOUT3B => open, CLKOUT4 => open, CLKOUT5 => open,
      CLKOUT6 => open, LOCKED => lock2, RST => reset2, PWRDWN => '0');
  -- Local feedback, as in the reused rgb2dvi ClockGen. Both serializer clocks
  -- share CLKOUT0; phase alignment with the upstream reference is unnecessary.
  fb2 <= fb2_raw;
  serial_buffer : BUFIO port map (I => serial_raw, O => serial_clk);
  pixel_buffer : BUFR
    generic map (BUFR_DIVIDE => "5", SIM_DEVICE => "7SERIES")
    port map (I => serial_raw, O => pixel_clk, CE => '1', CLR => not lock2);
  -- Upstream loss asserts reset2, forcing lock2 low. No counter decode crosses
  -- into the pixel reset bridges.
  video_hold <= not lock2;
  pattern_reset_bridge : entity work.ResetBridge
    port map (aRst => video_hold, OutClk => pixel_clk, oRst => video_reset);
  pattern : entity work.hdmi_colorbars_timing
    port map (pixel_clk => pixel_clk, reset => video_reset, rgb => rgb, hs => hs, vs => vs, de => de);
  transmitter : entity work.rgb2dvi
    generic map (kGenerateSerialClk => false, kRstActiveHigh => true)
    port map (TMDS_Clk_p => TMDS_clk_p, TMDS_Clk_n => TMDS_clk_n,
      TMDS_Data_p => TMDS_data_p, TMDS_Data_n => TMDS_data_n, oen => open,
      aRst => video_hold, aRst_n => '1', vid_pData => rgb, vid_pVDE => de,
      vid_pHSync => hs, vid_pVSync => vs, PixelClk => pixel_clk, SerialClk => serial_clk);
end architecture;
