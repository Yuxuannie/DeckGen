# Collateral Dataset

Manually-populated SCLD characterization collaterals, organized by `{node}/{lib_type}/`.

## Layout

```
collateral/
  {node}/                                    # e.g. N2P_v1.0, A14
    {lib_type}/                              # e.g. tcb02p_bwph130pnpnl3p48cpd_base_svt
      Char/                                  # char_*.tcl, *.inc, *.usage.l
      Template/                              # *.template.tcl
      Netlist/
        LPE_{rc}_{temp}/                     # netlists per RC type + temperature
          {CELL}_c.spi
      manifest.json                          # auto-generated, COMMITTED to git
```

## Populating

Drop SCLD files into `Char/`, `Template/`, `Netlist/` preserving SCLD-native filenames
(lib_type embedded). Do NOT rename files.

## Generating manifest.json

```bash
python3 tools/scan_collateral.py --node N2P_v1.0 --lib_type tcb02p_bwph130pnpnl3p48cpd_base_svt
python3 tools/scan_collateral.py --node N2P_v1.0 --all       # every lib_type under N2P_v1.0
python3 tools/scan_collateral.py --all                       # every (node, lib_type) leaf
```

The scanner also runs automatically whenever `CollateralStore` detects that
`Char/`, `Template/`, or `Netlist/` mtimes are newer than `manifest.json`.

## Git

`Char/`, `Template/`, `Netlist/` are gitignored. Only `manifest.json` and this README
are committed.
