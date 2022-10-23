#!/usr/bin/env python3

# Forked from
#   source https://gitlab.com/kicad/libraries/kicad-library-utils/-/tree/master/symbol-generators/avr_da_db
#   PR     https://gitlab.com/kicad/libraries/kicad-symbols/-/merge_requests/3448
#   commit https://gitlab.com/kicad/libraries/kicad-library-utils/-/commit/5c6e9c4574ab7c7e56e23f6ed55518021814e005
#   author https://gitlab.com/jhol Joel Holdsworth

####################################################################################################

"""
This script generates symbols for the AVR-DA and AVD-DB series of
microcontrollers from Microchip.

The script uses CSV files derived from the "I/O Multiplexing" tables in the
Reference Manual PDFs.

Usage: python3 make_avr_dy.py > MCU_Microchip_AVR_Dx.kicad_sym
"""

####################################################################################################

from collections import namedtuple, deque
from pathlib import Path
import math
import re
import string

####################################################################################################

from KiCadRW.sexp import symbol
from KiCadRW.sexp.symbol import SymbolLibrary, JustifyStyle, Part, ExtendedPart, Direction

####################################################################################################

Device = namedtuple('Device', 'family flash_size pin_count sram_size')
devices = [
    Device('DA', 32, 28, 4),
    Device('DA', 32, 32, 4),
    Device('DA', 32, 48, 4),
    Device('DA', 64, 28, 8),
    Device('DA', 64, 32, 8),
    Device('DA', 64, 48, 8),
    Device('DA', 64, 64, 8),
    Device('DA', 128, 28, 16),
    Device('DA', 128, 32, 16),
    Device('DA', 128, 48, 16),
    Device('DA', 128, 64, 16),
    Device('DB', 32, 28, 4),
    Device('DB', 32, 32, 4),
    Device('DB', 32, 48, 4),
    Device('DB', 64, 28, 8),
    Device('DB', 64, 32, 8),
    Device('DB', 64, 48, 8),
    Device('DB', 64, 64, 8),
    Device('DB', 128, 28, 16),
    Device('DB', 128, 32, 16),
    Device('DB', 128, 48, 16),
    Device('DB', 128, 64, 16),
]

device_doc_dir = 'https://ww1.microchip.com/downloads/en/DeviceDoc/'
pdfs = {
    (32, 'DA'): 'AVR32DA28-32-48-Data-Sheet-40002228B.pdf',
    (64, 'DA'): 'AVR64DA28-32-48-64-Data-Sheet-40002233B.pdf',
    (128, 'DA'): 'AVR128DA28-32-48-64-DataSheet-DS40002183B.pdf',
    (32, 'DB'): 'AVR32DB28-32-48-DataSheet-DS40002301A.pdf',
    (64, 'DB'): 'AVR64DB28-32-48-64-DataSheet-DS40002300A.pdf',
    (128, 'DB'): 'AVR128DB28-32-48-64-DataSheet-DS40002247A.pdf',
}

families = sorted({_.family for _ in devices})
family_descriptions = {'DA': 'Touch Sensing', 'DB': 'Op Amps and Multi-Voltage I/O'}

flash_sizes = sorted({_.flash_size for _ in devices})
pin_counts = sorted({_.pin_count for _ in devices})

max_freq = 24

packages = {
    28: ('SO', 'SP', 'SS'),
    32: ('PT', 'RXB'),
    48: ('PT', '6LX'),
    64: ('PT', 'MR'),
}

package_styles = {
    'MR': 'VQFN',
    '6LX': 'VQFN',
    'RXB': 'VQFN',
    'PT': 'TQFP',
    'SS': 'SSOP',
    'SO': 'SOIC',
    'SP': 'SPDIP',
}

Package = namedtuple('Package', 'style pin_count')
Footprint = namedtuple('Footprint', 'footprint footprint_filter')

footprints = {
    Package('SP', 28): Footprint('Package_DIP:DIP-28_W7.62mm', 'DIP*W7.62mm*'),
    Package('SO', 28): Footprint(
        'Package_SO:SOIC-28W_7.5x17.9mm_P1.27mm',
        'SOIC*7.5x17.9mm*P1.27mm*'
    ),
    Package('SS', 28): Footprint(
        'Package_SO:SSOP-28_5.3x10.2mm_P0.65mm',
        'SSOP*5.3x10.2mm*P0.65mm*'
    ),
    Package('RXB', 32): Footprint(
        'Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.1x3.1mm',
        'QFN*1EP*5x5mm*P0.5mm*EP3.1x3.1mm*',
    ),
    Package('PT', 32): Footprint(
        'Package_QFP:TQFP-32_7x7mm_P0.8mm',
        'TQFP*7x7mm*P0.8mm*'
    ),
    Package('6LX', 48): Footprint(
        'Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP4.2x4.2mm',
        'QFN*1EP*6x6mm*P0.4mm*EP4.2x4.2mm*',
    ),
    Package('PT', 48): Footprint(
        'Package_QFP:TQFP-48_7x7mm_P0.5mm',
        'TQFP*7x7mm*P0.5mm*'
    ),
    Package('MR', 64): Footprint(
        'Package_DFN_QFN:VQFN-64-1EP_9x9mm_P0.5mm_EP7.15x7.15mm',
        'VQFN*1EP*9x9mm*P0.5mm*EP7.15x7.15mm*',
    ),
    Package('PT', 64): Footprint(
        'Package_QFP:TQFP-64_10x10mm_P0.5mm',
        'TQFP*10x10mm*P0.5mm*'
    ),
}

####################################################################################################
#
# Read pins from CSV
#

Pin = namedtuple('Pin', 'number name special')

re_footnote = re.compile(r'\([0-9]+\)')

def load_pins(family: str, flash_size: int, pin_count: int, package: str) -> list[Pin]:
    def parse_line(line: str) -> Pin | None:
        cells = line.split(',')
        pin_num = cells[package_col]
        special = cells[special_col]
        if pin_num:
            return Pin(
                int(pin_num),
                re_footnote.sub('', cells[pin_name_col]),
                None if special == '' else special,
            )
        return None

    filename_pattern = f'avr{flash_size}{family.lower()}-io-mux.csv'
    path = Path(__file__).parent.joinpath(filename_pattern)
    with open(path, 'rt', encoding='utf8') as fh:
        heading_cells = fh.readline().rstrip().split(',')
        for i, col_name in enumerate(heading_cells):
            if f'{package}{pin_count}' in col_name.split('/'):
                package_col = i
        pin_name_col = heading_cells.index('Pin Name')
        special_col = heading_cells.index('Special')
        return [pin for pin in (parse_line(line) for line in fh) if pin]

####################################################################################################

PinBanks = namedtuple('PinBanks', 'power ground misc ports')
Port = namedtuple('Port', 'letter pins')

def bank_pins(pins: list[Pin]) -> PinBanks:
    def filter_port_pins(port: str) -> list[Pin]:
        port_name = 'P' + port
        return [pin for pin in pins if pin.name.startswith(port_name)]

    banks = PinBanks(
        [pin for pin in pins if 'VDD' in pin.name],
        [pin for pin in pins if 'GND' in pin.name],
        [pin for pin in pins if pin.name in ('UPDI',)],
        [
            p
            for p in (
                Port(letter, filter_port_pins(letter))
                for letter in string.ascii_uppercase
            )
            if p.pins
        ],
    )

    # Check for remaining pins
    remaining_pins = set(pins) - set(banks.power) - set(banks.ground) - set(banks.misc)
    for port in banks.ports:
        remaining_pins -= set(port.pins)
    if remaining_pins:
        remaining_pins = sorted(remaining_pins, key=lambda p: p.number)
        raise ValueError(
            'Some pins were not sorted into banks: ' +
            ', '.join(f'{p.number}:{p.name}' for p in remaining_pins)
        )

    return banks

####################################################################################################

def get_part_name(family: str, device: Device, package: str) -> str:
    return f'AVR{device.flash_size}{family}{device.pin_count}x-x{package}'

####################################################################################################

def has_exposed_pad(pin_count: int, package: str) -> bool:
    return '-1EP' in footprints[Package(package, pin_count)].footprint

####################################################################################################

grid = 2.54
width_padding = 6 * grid
height_padding = 2 * grid
pin_length = 1 * grid
font_width = 0.5 * grid
font_height = 0.5 * grid
text_offset = 0.5 * grid

####################################################################################################

def make_properties(
        part: Part, family: str, device: Device, package: str,
        width: float, height: float, value_offset: float,
) -> None:
    package_style = package_styles[package]
    footprint = footprints[Package(package, device.pin_count)]
    package_name = f'{package_style}-{device.pin_count}'
    part_name = get_part_name(family, device, package)

    description = (
        f'{max_freq}MHz, {device.flash_size}kB Flash, {device.sram_size}kB SRAM, EEPROM '
        f'with {family_descriptions[family]}, {package_name}'
    )
    datasheet = device_doc_dir + pdfs[(device.flash_size, family)]

    part.add_property(
        'Reference', 'U',
        at=(-width/2, height/2 + text_offset),
        font_size=(font_width, font_height),
        justify=JustifyStyle.LEFT | JustifyStyle.BOTTOM,
    )
    part.add_property(
        'Value', part_name,
        at=(value_offset, -height/2 - text_offset),
        font_size=(font_width, font_height),
        justify=JustifyStyle.LEFT | JustifyStyle.TOP,
    )
    part.add_property(
        'Footprint', footprint.footprint,
        font_size=(font_width, font_height),
        italic=True,
        hide=True,
    )
    part.add_property(
        'Datasheet', datasheet,
        font_size=(font_width, font_height),
        hide=True,
    )
    part.add_property(
        'ki_keywords',
        f'AVR 8bit Microcontroller AVR-{family}',
        font_size=(font_width, font_height),
        hide=True,
    )
    part.add_property(
        'ki_description', description,
        font_size=(font_width, font_height),
        hide=True,
    )
    part.add_property(
        'ki_fp_filters', footprint.footprint_filter,
        font_size=(font_width, font_height),
        hide=True,
    )

####################################################################################################

BaseInfo = namedtuple('BaseInfo', 'name width height value_offset')

def make_base_device(library: SymbolLibrary, family: str, device: Device, package: str) -> BaseInfo:
    # print()
    # print('make_base_device', family, device, package)
    part_name = get_part_name(family, device, package)
    package_style = package_styles[package]

    banks = bank_pins(
        load_pins(family, device.flash_size, device.pin_count, package_style)
    )

    # for bank in ('power', 'ground', 'misc'):
    #     print(f'- {bank}')
    #     for pin in getattr(banks, bank):
    #         print(' ', pin)
    # for port in banks.ports:
    #     print(f'- {port.letter}')
    #     for pin in port.pins:
    #         print(' ', pin)

    left_banks = []
    right_banks = []
    side_banks = deque([port.pins for port in banks.ports] + [banks.misc])

    # Fixme: side_width return for ground !
    def side_width(bank: list[Pin]) -> int:
        return len(banks.ground) - 1

    def side_height(banks: list[Pin]) -> int:
        if len(banks) == 0:
            return 0
        return sum((len(bank) + 1 for bank in banks), 0) - 2

    top_side_width = side_width(banks.power)
    bottom_side_width = side_width(banks.ground)
    inner_width = math.ceil(max(top_side_width, bottom_side_width) / 2) * 2 * grid
    outline_width = inner_width + width_padding * 2

    # dispatch ports on right and left side
    #   try to get the same number of pins on both side
    while side_banks:
        if side_height(left_banks) >= side_height(right_banks):
            right_banks.append(side_banks.popleft())
        else:
            left_banks.append(side_banks.pop())

    # Fixme: duplicate code
    inner_height = math.ceil(max(side_height(left_banks), side_height(right_banks)) / 2) * 2 * grid
    outline_height = inner_height + height_padding * 2

    left = -outline_width / 2
    right = -left
    top = outline_height / 2
    bottom = -top

    part = library.add_part(part_name)

    # Properties
    value_offset = (bottom_side_width // 2 + 1) * grid
    make_properties(part, family, device, package, outline_width, outline_height, value_offset)

    # Background
    part.add_rectangle(start=(left, top), end=(right, bottom))

    # Pins
    def make_pin_label(pin: Pin) -> str:
        if pin.special == 'RESET':
            return '~{RESET}/' + pin.name
        elif pin.special is not None and pin.special not in (
            'CLKOUT',
            'EXTCLK',
            'TWI',
            'TWI Fm+',
            'UPDI',
        ):
            special = pin.special
            if special == 'XTALHF1 EXTCLK':
                special = 'XTALHF1'
            return f'{special}/{pin.name}'
        return pin.name

    def directionality(pin: Pin) -> str:
        if pin.name in ('UPDI',):
            return 'input'
        return 'bidirectional'

    def render_pin(
            part: Part,
            type_: str, name: str, number: str,
            x: float, y: float, angle: int,
            hide: bool = False,
    ) -> symbol.Pin:
        part.add_pin(
            name=name,
            number=number,
            type_=type_,
            at=(x, y),
            angle=angle,
            length=pin_length,
            font_size=(font_width, font_height),
            hide=hide,
        )

    def render_side_banks(banks: list[Pin], x: float, angle: int) -> None:
        y = inner_height / 2
        for bank in banks:
            for pin in bank:
                render_pin(part, directionality(pin), make_pin_label(pin), pin.number, x, y, angle)
                y -= grid
            y -= grid

    def render_power_bank(pins: list[Pin], y: float, angle: int) -> None:
        def render_power_pin(name: str, number: str, stacked: bool = False) -> None:
            render_pin(
                part,
                'passive' if stacked else 'power_in',
                name, number, x, y, angle, hide=stacked,
            )
        pin_stacks = {}
        for p in pins:
            pin_stacks.setdefault(p.name, [])
            pin_stacks[p.name].append(p.number)
        x = -(len(pin_stacks) // 2) * grid
        for pin_name in sorted(pin_stacks):
            pin_numbers = sorted(pin_stacks[pin_name])
            render_power_pin(pin_name, pin_numbers[0])
            for pin_number in pin_numbers[1:]:
                render_power_pin(pin_name, pin_number, stacked=True)
            x += grid

    render_side_banks(right_banks, right + pin_length, Direction.LEFT)
    render_side_banks(left_banks, left - pin_length, Direction.RIGHT)
    render_power_bank(banks.power, top + pin_length, Direction.BOTTOM)

    ground_pins = banks.ground
    if has_exposed_pad(device.pin_count, package):
        ground_pins.append(Pin(device.pin_count + 1, 'GND', ''))
    render_power_bank(ground_pins, bottom - pin_length, Direction.TOP)

    return BaseInfo(part_name, outline_width, outline_height, value_offset)

####################################################################################################

def make_alias_device(
        library: SymbolLibrary,
        family: str, device: Device, package: str, base_info: str,
) -> ExtendedPart:
    part_name = get_part_name(family, device, package)
    part = library.add_extended_part(part_name, base_info.name)
    make_properties(
        part,
        family,
        device,
        package,
        base_info.width,
        base_info.height,
        base_info.value_offset,
    )
    return part

####################################################################################################

def main() -> SymbolLibrary:
    library = SymbolLibrary(version='20211014')

    for family in families:
        for pin_count in pin_counts:
            family_devices_with_pin_count = [d for d in devices if d.family == family and d.pin_count == pin_count]
            # base device has the smallest flash size
            base_device = family_devices_with_pin_count[0]

            packages_with_pin_count = packages[pin_count]

            # Process no exposed pad
            packages_with_no_exposed_pad = [p for p in packages_with_pin_count if not has_exposed_pad(pin_count, p)]
            base_package_with_no_exposed_pad = (
                packages_with_no_exposed_pad[0]
                if packages_with_no_exposed_pad
                else None
            )
            if base_package_with_no_exposed_pad:
                base_with_no_exposed_pad_info = make_base_device(library, family, base_device, base_package_with_no_exposed_pad)
            else:
                base_with_no_exposed_pad_info = None
            for alias_device in family_devices_with_pin_count:
                for package in packages_with_no_exposed_pad:
                    if (
                        alias_device != base_device
                        or package != base_package_with_no_exposed_pad
                    ):
                        make_alias_device(library, family, alias_device, package, base_with_no_exposed_pad_info)

            # Process with exposed pad
            packages_with_exposed_pad = [p for p in packages_with_pin_count if has_exposed_pad(pin_count, p)]
            base_package_with_exposed_pad = (
                packages_with_exposed_pad[0]
                if packages_with_exposed_pad
                else None
            )
            if base_package_with_exposed_pad:
                base_with_exposed_pad_info = make_base_device(library, family, base_device, base_package_with_exposed_pad)
            else:
                base_with_exposed_pad_info = None
            for alias_device in family_devices_with_pin_count:
                for package in packages_with_exposed_pad:
                    if (
                        alias_device != base_device
                        or package != base_package_with_exposed_pad
                    ):
                        make_alias_device(library, family, alias_device, package, base_with_exposed_pad_info)

    return library

####################################################################################################

if __name__ == '__main__':
    library = main()
    sexp_str = library.dumps()
    with open('out', 'w', encoding='utf8') as fh:
        fh.write(sexp_str)
