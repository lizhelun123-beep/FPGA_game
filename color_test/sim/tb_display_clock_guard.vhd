library ieee;
use ieee.std_logic_1164.all;

entity tb_display_clock_guard is end;
architecture test of tb_display_clock_guard is
  signal clk : std_logic := '0';
  signal resetn, locked, enabled, done, ready, synced : std_logic := '0';
  signal ref_run : boolean := true;
begin
  process begin
    wait for 5 ns;
    if ref_run then clk <= not clk; else clk <= '0'; end if;
  end process;
  dut: entity work.display_clock_guard
    port map (clk, resetn, locked, enabled, done, ready, synced);
  process
    procedure edges(n : positive) is
    begin
      for i in 1 to n loop wait until rising_edge(clk); wait for 1 ns; end loop;
    end;
    procedure check(value : std_logic; message_text : string) is
    begin assert ready=value report message_text severity failure; end;
  begin
    edges(3); check('0', "initial isolation");
    resetn <= '1'; locked <= '1'; edges(5);
    check('0', "initial lock is not a completed transaction");
    enabled <= '1'; edges(3); check('0', "enabled before completion");
    done <= '1'; edges(2); check('1', "fresh completion qualifies");
    -- Entire lock-low pulse is between clock edges. The asynchronous bridge
    -- must retain it and clock return alone must never restore READY.
    wait for 1 ns; locked <= '0'; wait for 1 ns;
    check('0', "brief lock loss isolates"); locked <= '1';
    edges(8); check('0', "clock return cannot requalify old completion");
    enabled <= '0'; done <= '0'; edges(2);
    enabled <= '1'; edges(2); done <= '1'; edges(2);
    check('1', "fresh recovery transaction");
    resetn <= '0'; done <= '1'; edges(1); check('0', "reset dominates completion");
    resetn <= '1'; edges(5); check('0', "old done after reset is not completion");
    enabled <= '0'; done <= '0'; edges(2);
    enabled <= '1'; edges(3); done <= '1'; edges(2); check('1', "restart after reset");
    enabled <= '0'; edges(1); check('0', "disable isolates");
    enabled <= '1'; edges(4); check('0', "old done after disable cannot qualify");
    done <= '0'; edges(2); done <= '1'; edges(2); check('1', "fresh done after disable");
    ref_run <= false; wait for 12 ns;
    locked <= '0'; wait for 1 ns;
    check('0', "lock loss isolates even with stopped reference");
    assert synced='0' report "shared lock bridge did not clear while stopped" severity failure;
    locked <= '1'; wait for 20 ns; check('0', "stopped reference cannot release");
    assert synced='0' report "shared bridge released without local edges" severity failure;
    ref_run <= true; edges(1);
    assert synced='0' report "bridge released after only one edge" severity failure;
    edges(1); assert synced='1' report "bridge failed to release after two edges" severity failure;
    edges(4); check('0', "reference return cannot reuse old done");
    done <= '0'; edges(2); done <= '1'; edges(2); check('1', "fresh post-stop transaction");
    report "PASS display_clock_guard: startup, completion, short loss, sticky isolation, recovery, reset overlap, disable" severity note;
    wait;
  end process;
end architecture;
