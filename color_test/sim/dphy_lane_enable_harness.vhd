-- Bounded integration harness, not an alternate production implementation.
-- Retain the canonical CSI PPI launch registers, D-PHY gating, lane chains,
-- AXI control, IDELAYCTRL and HS/byte clocks. Datapath outputs are observable
-- to keep the lane receive/reset logic in the OOC netlist.
library ieee;
use ieee.std_logic_1164.all;
library csi;
library dphy;
library unisim;
use unisim.vcomponents.all;

entity dphy_lane_enable_harness is
   generic (kPPISharedEnable : boolean := true);
   port (
      video_aclk, RefClk, s_axi_lite_aclk : in std_logic;
      video_aresetn, vEnable, aRst, s_axi_lite_aresetn : in std_logic;
      dphy_clk_hs_p, dphy_clk_hs_n, dphy_clk_lp_p, dphy_clk_lp_n : in std_logic;
      dphy_data_hs_p, dphy_data_hs_n : in std_logic_vector(1 downto 0);
      dphy_data_lp_p, dphy_data_lp_n : in std_logic_vector(1 downto 0);
      awvalid, wvalid, bready : in std_logic;
      awaddr : in std_logic_vector(3 downto 0);
      wdata : in std_logic_vector(31 downto 0);
      awready, wready, bvalid : out std_logic;
      bresp : out std_logic_vector(1 downto 0);
      ppi_enable : out std_logic_vector(2 downto 0);
      video_tdata : out std_logic_vector(39 downto 0);
      video_tvalid, video_tlast : out std_logic;
      video_tuser : out std_logic_vector(0 downto 0);
      video_tready : in std_logic := '1';
      rx_data : out std_logic_vector(15 downto 0);
      rx_valid, rx_active, rx_sync, rx_sot_error, rx_sotsync_error : out std_logic_vector(1 downto 0);
      byte_clk, serial_clk, clk_active, clk_stop : out std_logic
   );
end entity;

architecture integration of dphy_lane_enable_harness is
   signal clk_en, rx_byte_clk, rx_serial_clk, rx_clk_active, rx_clk_stop : std_logic;
   signal data_en, valid_hs, active_hs, sync_hs : std_logic_vector(1 downto 0);
   signal data_hs : std_logic_vector(15 downto 0);
   signal ref_buf, video_buf, axi_buf : std_logic;
begin
   -- OOC clock boundaries model the three existing PS FCLK global buffers.
   -- These are not additional production clocks or physical board inputs.
   RefGlobal: BUFG port map (I => RefClk, O => ref_buf);
   VideoGlobal: BUFG port map (I => video_aclk, O => video_buf);
   AxiGlobal: BUFG port map (I => s_axi_lite_aclk, O => axi_buf);
   csi_rx: entity csi.MIPI_CSI2_Rx
      generic map (kLaneCount => 2, kDebug => false)
      port map (
         video_aclk => video_buf, video_aresetn => video_aresetn, vEnable => vEnable,
         RxByteClkHS => rx_byte_clk, aClkStopstate => rx_clk_stop,
         aRxClkActiveHS => rx_clk_active, rbRxDataHS => data_hs,
         rbRxSyncHS => sync_hs, rbRxValidHS => valid_hs, rbRxActiveHS => active_hs,
         aDEnable => data_en, aClkEnable => clk_en,
         m_axis_video_tdata => video_tdata, m_axis_video_tvalid => video_tvalid,
         m_axis_video_tready => video_tready, m_axis_video_tlast => video_tlast,
         m_axis_video_tuser => video_tuser, CrcErrorCount => open, FrameCount => open,
         FifoOverflow => open);

   phy: entity dphy.MIPI_DPHY_Receiver
      generic map (
         kNoOfDataLanes => 2, kGenerateAXIL => true, kGenerateMMCM => false,
         kPPISharedEnable => kPPISharedEnable,
         kDebug => false, kLPFromLane0 => false, kRefClkFreqHz => 200_000_000)
      port map (
         RefClk => ref_buf, aRst => aRst,
         dphy_clk_hs_p => dphy_clk_hs_p, dphy_clk_hs_n => dphy_clk_hs_n,
         dphy_clk_lp_p => dphy_clk_lp_p, dphy_clk_lp_n => dphy_clk_lp_n,
         dphy_data_hs_p => dphy_data_hs_p, dphy_data_hs_n => dphy_data_hs_n,
         dphy_data_lp_p => dphy_data_lp_p, dphy_data_lp_n => dphy_data_lp_n,
         aClkEnable => clk_en, aD0Enable => data_en(0), aD1Enable => data_en(1),
         aClkForceRxmode => '0', aD0ForceRxmode => '0', aD1ForceRxmode => '0',
         RxByteClkHS => rx_byte_clk, RxDDRClkHS => rx_serial_clk,
         aRxClkActiveHS => rx_clk_active, aClkStopstate => rx_clk_stop,
         aClkUlpsActiveNot => open, aRxUlpsClkNot => open, aClkErrControl => open,
         aD0Stopstate => open, aD0UlpsActiveNot => open,
         rbD0RxDataHS => data_hs(7 downto 0), rbD0RxValidHS => valid_hs(0),
         rbD0RxActiveHS => active_hs(0), rbD0RxSyncHS => sync_hs(0),
         rbD0ErrSotHS => rx_sot_error(0), rbD0ErrSotSyncHS => rx_sotsync_error(0),
         D0RxClkEsc => open, aD0RxDataEsc => open, aD0RxValidEsc => open,
         aD0RxLpdtEsc => open, aD0RxUlpsEsc => open, aD0RxTriggerEsc => open,
         aD0ErrEsc => open, aD0ErrControl => open,
         aD1Stopstate => open, aD1UlpsActiveNot => open,
         rbD1RxDataHS => data_hs(15 downto 8), rbD1RxValidHS => valid_hs(1),
         rbD1RxActiveHS => active_hs(1), rbD1RxSyncHS => sync_hs(1),
         rbD1ErrSotHS => rx_sot_error(1), rbD1ErrSotSyncHS => rx_sotsync_error(1),
         D1RxClkEsc => open, aD1RxDataEsc => open, aD1RxValidEsc => open,
         aD1RxLpdtEsc => open, aD1RxUlpsEsc => open, aD1RxTriggerEsc => open,
         aD1ErrEsc => open, aD1ErrControl => open,
         s_axi_lite_aclk => axi_buf, s_axi_lite_aresetn => s_axi_lite_aresetn,
         s_axi_lite_awaddr => awaddr, s_axi_lite_awprot => "000",
         s_axi_lite_awvalid => awvalid, s_axi_lite_awready => awready,
         s_axi_lite_wdata => wdata, s_axi_lite_wstrb => "1111",
         s_axi_lite_wvalid => wvalid, s_axi_lite_wready => wready,
         s_axi_lite_bresp => bresp, s_axi_lite_bvalid => bvalid,
         s_axi_lite_bready => bready,
         s_axi_lite_araddr => "0000", s_axi_lite_arprot => "000",
         s_axi_lite_arvalid => '0', s_axi_lite_arready => open,
         s_axi_lite_rdata => open, s_axi_lite_rresp => open,
         s_axi_lite_rvalid => open, s_axi_lite_rready => '1');

   ppi_enable <= data_en & clk_en;
   byte_clk <= rx_byte_clk;
   serial_clk <= rx_serial_clk;
   clk_active <= rx_clk_active;
   clk_stop <= rx_clk_stop;
   rx_data <= data_hs;
   rx_valid <= valid_hs;
   rx_active <= active_hs;
   rx_sync <= sync_hs;
end architecture;
