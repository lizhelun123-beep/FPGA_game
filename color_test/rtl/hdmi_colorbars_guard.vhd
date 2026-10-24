-- Reference-clock reset supervisor. Power-on hold and a single reset pulse
-- after each observed LOCKED loss. No logic is clocked by LOCKED itself.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity hdmi_colorbars_guard is
  port (ref_clk, async_hold, locked : in std_logic; mmcm_reset : out std_logic);
end entity;

architecture rtl of hdmi_colorbars_guard is
  signal hold_sync : std_logic;
  signal lock_pipe : std_logic_vector(1 downto 0) := "00";
  signal countdown : unsigned(4 downto 0) := (others => '1');
  signal seen_lock : std_logic := '0';
  signal reset_request : std_logic := '1';
  attribute ASYNC_REG : string;
  attribute ASYNC_REG of lock_pipe : signal is "TRUE";
begin
  hold_bridge : entity work.ResetBridge
    port map (aRst => async_hold, OutClk => ref_clk, oRst => hold_sync);
  process(ref_clk)
  begin
    if rising_edge(ref_clk) then
      lock_pipe <= lock_pipe(0) & locked;
    end if;
  end process;
  -- Registered request avoids glitches from a combinational counter decode.
  -- Upstream loss asserts asynchronously; release waits for hold_bridge and
  -- the complete reference-clock hold interval.
  process(ref_clk, async_hold)
  begin
    if async_hold = '1' then
      countdown <= (others => '1'); seen_lock <= '0'; reset_request <= '1';
    elsif rising_edge(ref_clk) then
      if hold_sync = '1' then
        countdown <= (others => '1'); seen_lock <= '0'; reset_request <= '1';
      elsif countdown /= 0 then
        countdown <= countdown - 1; seen_lock <= '0'; reset_request <= '1';
      elsif lock_pipe(1) = '1' then
        seen_lock <= '1'; reset_request <= '0';
      elsif seen_lock = '1' then
        countdown <= (others => '1'); seen_lock <= '0'; reset_request <= '1';
      else
        reset_request <= '0';
      end if;
    end if;
  end process;
  mmcm_reset <= reset_request;
end architecture;
