-- Fixed diagnostic raster; no AXI, memory, camera or software dependency.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity hdmi_colorbars_timing is
  port (pixel_clk, reset : in std_logic;
        rgb : out std_logic_vector(23 downto 0);
        hs, vs, de : out std_logic);
end entity;

architecture rtl of hdmi_colorbars_timing is
  signal x : unsigned(10 downto 0) := (others => '0');
  signal y : unsigned(9 downto 0) := (others => '0');
begin
  process(pixel_clk)
    variable c : std_logic_vector(23 downto 0);
    variable h, v, active : std_logic;
  begin
    if rising_edge(pixel_clk) then
      if reset = '1' then
        x <= (others => '0'); y <= (others => '0');
        rgb <= (others => '0'); hs <= '0'; vs <= '0'; de <= '0';
      else
        h := '0'; v := '0'; active := '0'; c := x"000000";
        if x >= 1390 and x < 1430 then h := '1'; end if;
        if y >= 805 and y < 810 then v := '1'; end if;
        if x < 1280 and y < 800 then
          active := '1';
          if    x < 160 then c := x"FFFFFF";
          elsif x < 320 then c := x"FFFF00";
          elsif x < 480 then c := x"00FFFF";
          elsif x < 640 then c := x"00FF00";
          elsif x < 800 then c := x"FF00FF";
          elsif x < 960 then c := x"FF0000";
          elsif x < 1120 then c := x"0000FF";
          else c := x"000000"; end if;
          -- A one-pixel border makes any active-area cropping observable.
          if x = 0 or x = 1279 or y = 0 or y = 799 then c := x"FFFFFF"; end if;
          -- Distinct solid corner markers, inside the white border.
          if x > 8 and x < 25 and y > 8 and y < 25 then c := x"FF0000"; end if;
          if x > 1254 and x < 1271 and y > 8 and y < 25 then c := x"00FF00"; end if;
          if x > 8 and x < 25 and y > 774 and y < 791 then c := x"0000FF"; end if;
          if x > 1254 and x < 1271 and y > 774 and y < 791 then c := x"FFFF00"; end if;
        end if;
        -- All four outputs describe the SAME pixel, with the same register stage.
        rgb <= c; hs <= h; vs <= v; de <= active;
        if x = 1649 then
          x <= (others => '0');
          if y = 829 then y <= (others => '0'); else y <= y + 1; end if;
        else x <= x + 1; end if;
      end if;
    end if;
  end process;
end architecture;
