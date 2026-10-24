-- Fixed candidate boundary. Instantiates the production receiver, not a copy.
library ieee;
use ieee.std_logic_1164.all;
library unisim;
use unisim.vcomponents.all;
entity dphy_sampling_ooc is
   port (
      dphy_clk_hs_p, dphy_clk_hs_n, dphy_clk_lp_p, dphy_clk_lp_n : in std_logic;
      dphy_data_hs_p, dphy_data_hs_n, dphy_data_lp_p, dphy_data_lp_n : in std_logic_vector(1 downto 0);
      refclk, rst, enable : in std_logic;
      data0, data1 : out std_logic_vector(7 downto 0);
      valid0, valid1, ready, byteclk : out std_logic);
end;
architecture fixed of dphy_sampling_ooc is
   signal ctlclk : std_logic;
begin
   RefBuffer: BUFG port map (I=>refclk,O=>ctlclk);
   phy: entity work.MIPI_DPHY_Receiver
      generic map (kNoOfDataLanes=>2,kBUFH_DDIRECT_M3=>true,
         kDebug=>false,kGenerateAXIL=>false,kLPFromLane0=>false,kPPISharedEnable=>true)
      port map (
         dphy_clk_hs_p=>dphy_clk_hs_p,dphy_clk_hs_n=>dphy_clk_hs_n,
         dphy_clk_lp_p=>dphy_clk_lp_p,dphy_clk_lp_n=>dphy_clk_lp_n,
         dphy_data_hs_p=>dphy_data_hs_p,dphy_data_hs_n=>dphy_data_hs_n,
         dphy_data_lp_p=>dphy_data_lp_p,dphy_data_lp_n=>dphy_data_lp_n,
         RefClk=>ctlclk,aRst=>rst,aClkEnable=>enable,aD0Enable=>enable,aD1Enable=>enable,
         aClkForceRxmode=>'0',aD0ForceRxmode=>'0',aD1ForceRxmode=>'0',
         rbD0RxDataHS=>data0,rbD1RxDataHS=>data1,
         rbD0RxValidHS=>valid0,rbD1RxValidHS=>valid1,
         RxByteClkHS=>byteclk,aRxClkActiveHS=>ready,
         s_axi_lite_aclk=>ctlclk,s_axi_lite_aresetn=>'1',
         s_axi_lite_awaddr=>(others=>'0'),s_axi_lite_awprot=>"000",
         s_axi_lite_awvalid=>'0',s_axi_lite_wdata=>(others=>'0'),
         s_axi_lite_wstrb=>(others=>'0'),s_axi_lite_wvalid=>'0',s_axi_lite_bready=>'0',
         s_axi_lite_araddr=>(others=>'0'),s_axi_lite_arprot=>"000",
         s_axi_lite_arvalid=>'0',s_axi_lite_rready=>'0');
end;
