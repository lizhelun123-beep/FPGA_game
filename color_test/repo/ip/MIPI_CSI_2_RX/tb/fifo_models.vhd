-- Simulation-only behavioral models for legacy 2017.4 FIFO IPs. The packaged
-- XCI files are locked in Vivado 2023.1, so their output products cannot be
-- regenerated for a clean behavioral test.
library ieee;
use ieee.std_logic_1164.all;

entity cdc_fifo is
   port (
      m_aclk : in std_logic;
      s_aclk : in std_logic;
      s_aresetn : in std_logic;
      s_axis_tvalid : in std_logic;
      s_axis_tready : out std_logic;
      s_axis_tdata : in std_logic_vector(31 downto 0);
      s_axis_tkeep : in std_logic_vector(3 downto 0);
      s_axis_tlast : in std_logic;
      m_axis_tvalid : out std_logic;
      m_axis_tready : in std_logic;
      m_axis_tdata : out std_logic_vector(31 downto 0);
      m_axis_tkeep : out std_logic_vector(3 downto 0);
      m_axis_tlast : out std_logic
   );
end cdc_fifo;

architecture simulation of cdc_fifo is
begin
   model: process
      type data_mem_t is array (0 to 31) of std_logic_vector(31 downto 0);
      type keep_mem_t is array (0 to 31) of std_logic_vector(3 downto 0);
      variable data_mem : data_mem_t;
      variable keep_mem : keep_mem_t;
      variable last_mem : std_logic_vector(0 to 31);
      variable wr_ptr, rd_ptr, count : natural range 0 to 32 := 0;
      variable do_push, do_pop : boolean;
   begin
      wait on s_aclk, m_aclk, s_aresetn;
      if s_aresetn = '0' then
         wr_ptr := 0;
         rd_ptr := 0;
         count := 0;
         s_axis_tready <= '1';
         m_axis_tvalid <= '0';
         m_axis_tdata <= (others => '0');
         m_axis_tkeep <= (others => '0');
         m_axis_tlast <= '0';
      else
         do_pop := rising_edge(m_aclk) and m_axis_tready = '1' and count > 0;
         do_push := rising_edge(s_aclk) and s_axis_tvalid = '1' and count < 32;
         if do_pop then
            rd_ptr := (rd_ptr + 1) mod 32;
            count := count - 1;
         end if;
         if do_push then
            data_mem(wr_ptr) := s_axis_tdata;
            keep_mem(wr_ptr) := s_axis_tkeep;
            last_mem(wr_ptr) := s_axis_tlast;
            wr_ptr := (wr_ptr + 1) mod 32;
            count := count + 1;
         end if;
         if count > 0 then
            m_axis_tvalid <= '1';
            m_axis_tdata <= data_mem(rd_ptr);
            m_axis_tkeep <= keep_mem(rd_ptr);
            m_axis_tlast <= last_mem(rd_ptr);
         else
            m_axis_tvalid <= '0';
         end if;
         if count < 32 then
            s_axis_tready <= '1';
         else
            s_axis_tready <= '0';
         end if;
      end if;
   end process;
end simulation;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity line_buffer is
   port (
      s_axis_aresetn : in std_logic;
      s_axis_aclk : in std_logic;
      s_axis_tvalid : in std_logic;
      s_axis_tready : out std_logic;
      s_axis_tdata : in std_logic_vector(39 downto 0);
      s_axis_tlast : in std_logic;
      s_axis_tuser : in std_logic_vector(0 downto 0);
      m_axis_tvalid : out std_logic;
      m_axis_tready : in std_logic;
      m_axis_tdata : out std_logic_vector(39 downto 0);
      m_axis_tlast : out std_logic;
      m_axis_tuser : out std_logic_vector(0 downto 0);
      axis_wr_data_count : out std_logic_vector(31 downto 0);
      axis_rd_data_count : out std_logic_vector(31 downto 0)
   );
end line_buffer;

architecture simulation of line_buffer is
   type data_mem_t is array (0 to 31) of std_logic_vector(39 downto 0);
   signal data_mem : data_mem_t;
   signal last_mem, user_mem : std_logic_vector(0 to 31);
   signal wr_ptr, rd_ptr : natural range 0 to 31 := 0;
   signal count : natural range 0 to 32 := 0;
begin
   s_axis_tready <= '1' when s_axis_aresetn = '1' and count < 32 else '0';
   m_axis_tvalid <= '1' when s_axis_aresetn = '1' and count > 0 else '0';
   m_axis_tdata <= data_mem(rd_ptr);
   m_axis_tlast <= last_mem(rd_ptr);
   m_axis_tuser(0) <= user_mem(rd_ptr);
   axis_wr_data_count <= std_logic_vector(to_unsigned(count, 32));
   axis_rd_data_count <= std_logic_vector(to_unsigned(count, 32));

   model: process(s_axis_aclk)
      variable next_count : natural range 0 to 32;
      variable do_push, do_pop : boolean;
   begin
      if rising_edge(s_axis_aclk) then
         if s_axis_aresetn = '0' then
            wr_ptr <= 0;
            rd_ptr <= 0;
            count <= 0;
         else
            do_push := s_axis_tvalid = '1' and count < 32;
            do_pop := m_axis_tready = '1' and count > 0;
            next_count := count;
            if do_pop then
               rd_ptr <= (rd_ptr + 1) mod 32;
               next_count := next_count - 1;
            end if;
            if do_push then
               data_mem(wr_ptr) <= s_axis_tdata;
               last_mem(wr_ptr) <= s_axis_tlast;
               user_mem(wr_ptr) <= s_axis_tuser(0);
               wr_ptr <= (wr_ptr + 1) mod 32;
               next_count := next_count + 1;
            end if;
            count <= next_count;
         end if;
      end if;
   end process;
end simulation;
