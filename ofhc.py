# CFD Bottleneck Estimator
# This program estimates the primary hardware bottlenecks for an OpenFOAM CFD simulation
# based on the number of cells and user-provided hardware specifications.

# ----- Define Constants -------------------------------------------------------------------------------------------- #

num_cells = NUM_CELLS = 10_000_000  # Number of cells in the CFD simulation
RAM_CAPACITY_GB = 64  # RAM Capacity in gigabyte
NUM_RAM_CHANNELS = 4  # Number of RAM channels
RAM_SPEED_MTS = 2133  # RAM speed in mega transfers per second
NUM_PROCESSORS = 2  # Number of physical processors
CPU_SPEED_GHZ = 2.2  # CPU clock-speed in gigahertz
NUM_CPU_CORES_PER_PROCESSOR = 10  # Number of CPU cores
L3_CACHE_CAPACITY_MB_PER_PROCESSOR = 25  # Size of the CPU L3 cache in megabytes
GPU_VRAM_GB = 0  # Virtual memory of the graphics card in gigabytes


# ----- Define Functions -------------------------------------------------------------------------------------------- #

def estimate_bottleneck_cpu_count(num_cells, num_processors, num_cpu_cores):
    # There should be approximately between 50,000 and 100,000 cells per core
    min_cells_per_core = 50_000
    actual_cells_per_core = num_cells / (num_cpu_cores * num_processors)
    min_ratio_cpu_count = min_cells_per_core / actual_cells_per_core
    if min_ratio_cpu_count > 1:
        print(f"Do not use all cores for computing. Limit the simulation to {round(num_cells / min_ratio_cpu_count)}")
    max_cells_per_core = 100_000
    required_num_cores = num_cells / max_cells_per_core
    return checked_requirements('CPU Cores', num_cpu_cores * num_processors, required_num_cores)


def estimate_bottleneck_cpu_speed(cpu_speed_ghz):
    # OpenFOAM solvers scale weakly with clock speed. Speeds between 1.5 and 2.0 GHz are acceptable, but faster clocks
    # reduce iteration time almost linearly up to ~3.5 GHz. A baseline ratio can be set against 3.0 GHz as reference.
    reference_ghz = 3.0
    return checked_requirements('CPU Clock-Speed (GHZ)', cpu_speed_ghz, reference_ghz)


def estimate_bottleneck_cpu_l3_cache(num_cpu_cores, num_cores, cpu_l3_cache_capacity_mb):
    # Performance drops when the working set spills beyond the L3 cache. For SIMPLE steady-state simulations around 100
    # bytes per cell are reused per iteration. Only a fraction fits in cache, but ≥2 MB / core is a practical baseline.
    reference_mb_per_core = 2
    required_cache_mb = num_cpu_cores * num_cores * reference_mb_per_core
    return checked_requirements('CPU L3 Cache (MB)', cpu_l3_cache_capacity_mb, required_cache_mb)


def estimate_bottleneck_ram_capacity(num_cells, actual_ram_capacity_gb):
    # Approximate requirements are 1.5 to 4.0 GB of RAM per million cells
    min_gb_ram_per_million_cells = 2
    required_ram_capacity_gb = (num_cells / 1_000_000) * min_gb_ram_per_million_cells
    return checked_requirements('RAM Capacity (GB)', actual_ram_capacity_gb, required_ram_capacity_gb)


def estimate_bottleneck_ram_channels(num_processors, num_cores, num_ram_channels):
    # Approximate requirements are 2-4 cores per channel
    max_cores_per_ram_channel = 4
    required_channels = (num_cores * num_processors) / max_cores_per_ram_channel
    return checked_requirements('RAM Channels', num_ram_channels, required_channels)


def estimate_bottleneck_ram_bandwidth(num_processors, num_cpu_cores, ram_speed_mts, num_ram_channels):
    # Published benchmarks (e.g. PRACE best practice guides, CFDDirect hardware studies) show solver performance
    # saturates when available memory bandwidth per core falls below ~1.5–2.5 GB/s.
    required_bandwidth_per_core_gbs = 2
    bytes_per_transfer = 8
    theoretical_bandwidth_gbs = ram_speed_mts * 1e6 * bytes_per_transfer * num_ram_channels / 1e9
    bandwidth_efficiency = 0.7  # Intel and AMD tuning guides noting ~65–75%
    actual_bandwidth_gbs = theoretical_bandwidth_gbs * bandwidth_efficiency
    required_bandwidth_gbs = num_processors * num_cpu_cores * required_bandwidth_per_core_gbs
    return checked_requirements('RAM Bandwidth (GB/s)', actual_bandwidth_gbs, required_bandwidth_gbs)


def estimate_gpu_vram_recommendations(num_cells, gpu_vram_gb):
    # For rendering, it can be useful to have 1 GB of VRAM per 12 million cells
    recommended_vram_gb_per_million_cells = 1 / 12
    recommended_vram_gb = num_cells / 1_000_000 * recommended_vram_gb_per_million_cells
    return checked_requirements('Virtual RAM (GB)', gpu_vram_gb, recommended_vram_gb)


def estimate_storage_requirements(num_cells, write_speed_gbs, actual_storage_capacity_gb):
    # Approximate space requirements are 1 GB per 1 million cells
    space_requirements_gb = num_cells / 1_000_000
    write_time_requirements_s = space_requirements_gb / write_speed_gbs
    print(f'Each time step will use approximately {write_time_requirements_s} seconds to write and '
          f'{space_requirements_gb} gigabytes to save')


def checked_requirements(title, numerator, denominator):
    ratio = numerator / denominator
    mark = '[✗]' if ratio < 1 else '[✓]'
    ratio_fmt = f'{round(ratio * 100)} %'

    def fmt(val):
        if isinstance(val, (int, float)):
            if val == 0:
                return "0"
            digits = 3 - int(f"{int(abs(val))}".__len__())
            digits = max(digits, 0)
            return f"{val:,.{digits}f}"
        return str(val)

    actual_fmt = fmt(numerator)
    target_fmt = fmt(denominator)
    return ratio, ratio_fmt, title, actual_fmt, target_fmt, mark


# ----- Define Main Function ---------------------------------------------------------------------------------------- #

def estimate_cfd_requirements(
        num_cells,
        ram_capacity_gb,
        num_ram_channels,
        ram_speed_mts,
        num_processors,
        num_cpu_cores,
        cpu_speed_ghz,
        cpu_l3_cache_capacity_mb,
        gpu_vram_gb):
    functions = [
        estimate_bottleneck_ram_capacity(num_cells, ram_capacity_gb),
        estimate_bottleneck_ram_channels(num_processors, num_cpu_cores, num_ram_channels),
        estimate_bottleneck_ram_bandwidth(num_processors, num_cpu_cores, ram_speed_mts, num_ram_channels),
        estimate_bottleneck_cpu_count(num_cells, num_processors, num_cpu_cores),
        estimate_bottleneck_cpu_speed(cpu_speed_ghz),
        estimate_bottleneck_cpu_l3_cache(num_processors, num_cpu_cores, cpu_l3_cache_capacity_mb),
        estimate_gpu_vram_recommendations(num_cells, gpu_vram_gb)]

    functions = sorted(functions, key=lambda f: f[0])

    for ratio, ratio_fmt, title, actual_fmt, target_fmt, mark in functions:
        print(f'{title:<22} Actual: {actual_fmt:<10} Target: {target_fmt:<10} {ratio_fmt:<5} {mark:<5}')


# ----- Define Program Execution ------------------------------------------------------------------------------------ #

if __name__ == '__main__':
    print(f'Checking the various possible hardware bottlenecks for a simulation with {NUM_CELLS:,} cells')

    estimate_cfd_requirements(
        num_cells=NUM_CELLS,
        ram_capacity_gb=RAM_CAPACITY_GB,
        num_ram_channels=NUM_RAM_CHANNELS,
        ram_speed_mts=RAM_SPEED_MTS,
        num_processors=NUM_PROCESSORS,
        num_cpu_cores=NUM_CPU_CORES_PER_PROCESSOR,
        cpu_speed_ghz=CPU_SPEED_GHZ,
        cpu_l3_cache_capacity_mb=L3_CACHE_CAPACITY_MB_PER_PROCESSOR,
        gpu_vram_gb=GPU_VRAM_GB)
