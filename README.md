# Line Distance Fiji Tool
A Fiji/ImageJ script for measuring mitochondrial shape, distances between endoplasmic reticulum (ER) and mitochondria, and distances between mitochondrial cristae. It works from manually drawn ROIs in the ImageJ ROI Manager and provides optional distance maps for visual quality assessment.
## Requirements
- [Fiji](https://fiji.sc/) with its ImageJ, Script Editor, and Python (Jython) support.
- A 2D image and manually drawn area and line ROIs. The script does not segment or identify structures from image pixels.
The script uses Fiji's Java APIs and Jython; it is not intended to run with a standalone Python interpreter.
## Getting started
1. Download `Line_Distance_v02.py` from this repository.
2. Open your image in Fiji. Set its spatial calibration using **Analyze > Set Scale**, or verify the calibration already stored in the image. Measurements use the image's pixel width, pixel height, and unit; an uncalibrated image is measured in pixels.
3. Open the ROI Manager via **Analyze > Tools > ROI Manager**.
4. Draw each mitochondrial outline as a closed area ROI and add it to the ROI Manager. Draw each crista or ER structure as a line ROI and add it as well. Use ROIs for the image you want to analyze; the tool processes the entire ROI Manager, not just selected entries.
5. Open `Line_Distance_v02.py` in Fiji's Script Editor, select **Python** as the language if needed, and click **Run**. A **Mito / Cristae / ER Distance** window opens.
6. With the intended image active, click **Check + Rename ROIs** and inspect the reported classifications. Adjust the ROIs if necessary.
7. Optionally select **Show QA distance maps**, **Save CSV**, or **Save TXT**. For file export, choose a save folder. Click **Analyze** to produce the result tables.
At least one valid mitochondrial area ROI and one valid line ROI are required for analysis. Save a copy of your ROIs from the ROI Manager before checking or analyzing if you need to preserve their original names.
## ROI classification
Classification is based on geometry, not ROI names:
- Non-line ROIs with at least three outline points are treated as mitochondria. Polygon, freehand, rectangle, oval, and traced area ROIs can be used.
- Straight, segmented, freehand line, and angle ROIs with at least two points are treated as lines. A line entirely inside or on a mitochondrial boundary is classified as a crista. Other lines, including lines crossing a boundary, are classified as ER.
- Other ROIs are ignored. Invalid lines and ignored ROIs are reported in the check dialog or Fiji log.
For each line, the tool prefers an enclosing mitochondrion over an intersecting one, and an intersecting mitochondrion over an outside one. Within the same relationship category, it chooses the smallest line-to-boundary distance. Thus, for an outside ER line the assigned mitochondrion is the closest boundary; for an intersecting line, relationship priority applies and the minimum distance is zero. Overlapping mitochondria and touching or crossing lines should be checked carefully.
**Check + Rename ROIs** and **Analyze** rename entries in the ROI Manager:
| Structure | Assigned name |
| --- | --- |
| Mitochondrion | `Mito_1`, `Mito_2`, ... |
| Crista inside a mitochondrion | `Cris_1-Mito_1`, `Cris_2-Mito_1`, ... |
| ER or other non-internal line | `ER_1`, `ER_2`, ... |
Mitochondria and ER are numbered in ROI Manager order; crista numbering restarts for each mitochondrion. Names may change if ROIs are added, removed, or reordered. ROI Manager indices in the results are one-based.
## Results
Each analysis appends rows to three named ImageJ results tables. Rows include the image title and a timestamp-based **Measurement Set** identifier (`Run_yyyyMMdd_HHmmss`), so repeated runs can be distinguished. Runs started within the same second can have the same identifier.
### Mitochondria Measurements
One row per mitochondrial area ROI reports area, perimeter, Feret length and width, aspect ratio, circularity, equivalent diameter, and ROI Manager index. Area and perimeter are calculated from the ROI outline. Feret length is the maximum distance between convex-hull points; Feret width is the minimum caliper width over hull edge orientations. Aspect ratio is Feret length divided by Feret width, circularity is `4 * pi * area / perimeter^2`, and equivalent diameter is `sqrt(4 * area / pi)`.
### Endoplasmic Reticulum Distance to Closest Mitochondrion
One row per ER line reports its length, assigned mitochondrion, relationship, and minimum, average, and maximum distances to that mitochondrial boundary. The minimum is the exact minimum between line and boundary segments. The average and maximum are calculated from points sampled along the ER line, each measured to the closest point on the boundary. A line intersecting the boundary has a minimum distance of zero.
### Cristae Distances (NN = Nearest Neighbor)
One row per crista reports its length, the number of cristae in its mitochondrion, and up to two nearest cristae in that same mitochondrion (**NN1** and **NN2**). By default, neighbors are ranked by their average distance. Each minimum is the exact minimum between the two polylines. Average and maximum distances use samples from both lines: each sample is measured to the closest point on the other line, then both sets of distances are combined. Missing neighbors have blank fields. Crista-to-mitochondrion distances are not reported.
When no ER or no cristae are found, the corresponding table contains a placeholder row. Distances and lengths use the calibrated image unit, and areas use its square. Coordinates are scaled independently by pixel width and height, so the geometry calculations support non-square pixels.
## Saving results and viewing ROIs
- **Save CSV** and **Save TXT** write the new rows to files in the chosen folder; TXT files are tab-delimited. Both options can be selected. A folder prompt appears on analysis if needed; cancelling it leaves the tables visible but does not save them.
- Files are named after the tables with punctuation replaced by underscores, for example `Mitochondria_Measurements.csv`. Existing files are appended to, not overwritten, and headers are written only for new or empty files. Use separate folders or files for datasets with different calibration units or column schemas, since existing headers are not checked.
- Results tables also accumulate rows across analyses while open. Save or clear them as appropriate before starting a new dataset. File-save errors are reported in the Fiji log.
- **Hide Mitos / Show Mitos**, **Hide Lines / Show Lines**, **Show All**, and **Hide All** control the displayed overlay. Mitochondrial outlines are green and lines are cyan by default. Refreshing this overlay replaces the image's existing overlay.
- **Clear ROIs** clears the ROI Manager and the current image overlay without a confirmation prompt. Save any needed ROIs first.
## Distance-map quality assessment
Enable **Show QA distance maps** before analysis to open maps for ER-to-assigned-mitochondrion and crista nearest-neighbor pairs. These are visual aids, not the source of the reported distances: they are computed from rasterized, one-pixel-wide outlines or lines using ImageJ's Euclidean distance map. At most 300 map windows are opened per run by default.
For square pixels, map values are scaled by the pixel width. For non-square pixels, map values remain in pixel-distance units even though the image calibration is copied; use the results tables for calibrated distances. Maps can consume substantial memory and screen space, so leave this option off for large ROI sets unless needed.
## Configuration
Edit the settings near the top of `Line_Distance_v02.py` before running the script:
| Setting | Default | Effect |
| --- | --- | --- |
| `SAMPLE_SPACING_PX` | `1.0` | Approximate sampling spacing in pixels for classification and sampled distance statistics. |
| `USE_COLORED_OVERLAY` | `True` | Color mitochondrial and line overlays green and cyan. |
| `RANK_CRISTAE_BY_AVERAGE_DISTANCE` | `True` | Rank crista neighbors by average distance; set to `False` to rank by minimum distance. |
| `MAX_DISTANCE_MAPS` | `300` | Maximum number of QA map windows per analysis. |
Sampling is performed along each line segment in pixel coordinates; the resulting average and maximum are sampled estimates, not continuous extrema. Smaller spacing increases computation. The tool analyzes 2D ROI coordinates and does not calculate 3D distances or track structures across image slices.
## Troubleshooting
- **No image or ROIs found:** Activate the intended image, then check that the ROI Manager contains at least one valid area and one valid line.
- **Unexpected classification:** Use **Check + Rename ROIs** to inspect assignments. Lines crossing a mitochondrial boundary are ER, while lines entirely inside or on it are cristae. All eligible area ROIs are treated as mitochondria.
- **Unexpected units or distances:** Verify image calibration before analysis and confirm that the ROIs belong to the active image. QA maps are rasterized and may differ from the geometry-based results.
- **No output files:** Select an export format and a folder, then inspect Fiji's log for save errors. Tables are still displayed if folder selection is cancelled.
## Repository contents
- `Line_Distance_v02.py` — Fiji/Jython script containing the interface, ROI classification, measurement, export, and QA-map logic.
