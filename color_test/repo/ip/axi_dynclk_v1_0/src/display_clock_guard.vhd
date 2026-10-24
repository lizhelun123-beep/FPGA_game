library ieee;
use ieee.std_logic_1164.all;

-- One RefClk/S_AXI-domain lock bridge shared by both DRP FSMs and READY.
-- External raw LOCKED_O and transaction-complete STAT[0] retain their ABI.
entity display_clock_guard is
  port (
    clk, resetn, locked, enabled, transaction_done : in std_logic;
    ready : out std_logic;
    synchronized_locked : out std_logic
  );
end entity;

architecture rtl of display_clock_guard is
  signal lock_sync : std_logic_vector(1 downto 0) := "00";
  signal done_previous : std_logic := '0';
  signal qualified : std_logic := '0';
  signal armed : std_logic := '0';
  attribute ASYNC_REG : string;
  attribute ASYNC_REG of lock_sync : signal is "TRUE";
begin
  -- Even a lock-low pulse between reference edges clears the qualification
  -- pipeline. Release needs two reference edges; the event is then latched
  -- by qualified, so clock return alone cannot republish the display.
  process(clk, locked)
  begin
    if locked = '0' then
      lock_sync <= "00";
    elsif rising_edge(clk) then
      if resetn = '0' then lock_sync <= "00";
      else lock_sync <= lock_sync(0) & '1'; end if;
    end if;
  end process;
  synchronized_locked <= lock_sync(1);
  process(clk)
  begin
    if rising_edge(clk) then
      done_previous <= transaction_done;
      if resetn = '0' then done_previous <= '0'; end if;
    end if;
  end process;
  -- A single register drives downstream reset bridges, without an AND gate.
  -- Bridge-to-qualified CLR release is local and must remain timed.
  process(clk, lock_sync(1))
  begin
    if lock_sync(1) = '0' then
      qualified <= '0'; armed <= '0';
    elsif rising_edge(clk) then
      if resetn = '0' or enabled = '0' then
        qualified <= '0'; armed <= '0';
      elsif transaction_done = '0' then
        armed <= '1';
      elsif armed = '1' and done_previous = '0' then
        qualified <= '1'; armed <= '0';
      end if;
    end if;
  end process;
  ready <= qualified;
end architecture;
