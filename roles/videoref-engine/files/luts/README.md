# LUT Presets for Color Grading

ffmpeg applies these via: `ffmpeg -i input.mp4 -vf lut3d=file=preset.cube output.mp4`

## Available presets

| Name | Description | Use case |
|------|-------------|----------|
| teal-orange | Blockbuster teal/orange split toning | Action, thriller |
| warm-vintage | Warm vintage film look | Nostalgia, romance |
| cold-blue | Cold desaturated blue | Sci-fi, horror |
| bleach-bypass | High contrast, desaturated | Drama, noir |
| golden-hour | Warm golden tones | Outdoor, sunset |

## Adding custom LUTs

Drop any `.cube` file in this directory. Use `vref produce-step $JOB colorgrade --lut <name>` to apply.
Export from Photoshop, DaVinci Resolve, or GIMP (Hald CLUT).
