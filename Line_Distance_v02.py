import math

import ij.IJ as IJ
from ij import ImagePlus, WindowManager
from ij.plugin.frame import RoiManager
from ij.measure import ResultsTable
from ij.gui import Roi, Overlay
from ij.process import ByteProcessor
from ij.plugin.filter import EDM
from ij.io import DirectoryChooser

from javax.swing import JFrame, JButton, JPanel, JCheckBox, BoxLayout, JLabel
from java.awt import FlowLayout, Color
import java.awt.Window as Window

from java.text import SimpleDateFormat
from java.util import Date
from java.io import File, FileWriter, BufferedWriter


# ============================================================
# Settings
# ============================================================

# Sampling density for line-to-boundary and line-to-line measurements.
# 1.0 means roughly every pixel along the line.
SAMPLE_SPACING_PX = 1.0

# Overlay colors for display.
USE_COLORED_OVERLAY = True

# If True, cristae nearest-neighbor lines are ranked by average distance.
# This is usually better than minimum distance, which can be biased by endpoints.
RANK_CRISTAE_BY_AVERAGE_DISTANCE = True

# Safety limit to avoid accidentally opening hundreds/thousands of distance maps.
MAX_DISTANCE_MAPS = 300

TABLE_MITO = "Mitochondria Measurements"
TABLE_ER = "Endoplasmic Reticulum Distance to Closest Mitochondrion"
TABLE_CRISTAE = "Cristae Distances (NN = Nearest Neighbor)"


# ============================================================
# ASCII-safe text helpers
# ============================================================

def ascii_text(x):
    """
    Convert text to safe ASCII for Jython/ImageJ tables/logs.
    Replaces micro symbols with 'u', so micrometer units become um.
    """
    if x is None:
        return ""

    try:
        s = unicode(x)
    except:
        try:
            s = str(x)
        except:
            return ""

    # Replace common micro symbols with ASCII u.
    s = s.replace(u"\xb5", "u")      # micro sign
    s = s.replace(u"\u03bc", "u")    # Greek mu

    try:
        return s.encode("ascii", "replace")
    except:
        try:
            return str(s)
        except:
            return ""


def ascii_unit(unit):
    s = ascii_text(unit).strip()

    if s == "":
        return "pixel"

    return s


def safe_title(s):
    """
    Make a safe short window/file title.
    """
    s = ascii_text(s)
    out = []

    for ch in s:
        if ch.isalnum() or ch in ["_", "-"]:
            out.append(ch)
        else:
            out.append("_")

    title = "".join(out)

    while "__" in title:
        title = title.replace("__", "_")

    title = title.strip("_")

    if len(title) > 180:
        title = title[:180]

    if title == "":
        title = "Table"

    return title


# ============================================================
# Remove old duplicated tool windows
# ============================================================

for w in Window.getWindows():
    if w.getName() == "MitoCristaeDistanceToolFrame":
        w.dispose()


# ============================================================
# Basic helpers
# ============================================================

def get_current_image():
    try:
        return IJ.getImage()
    except:
        return None


def get_rm():
    rm = RoiManager.getInstance()
    if not rm:
        rm = RoiManager()
    return rm


def safe_name(roi, fallback):
    name = ascii_text(roi.getName()).strip()

    if name == "":
        return fallback

    return name


def is_nan(x):
    try:
        return x != x
    except:
        return False


def safe_number_for_sort(x):
    if is_nan(x):
        return float("inf")
    return x


def make_measurement_set_id():
    """
    Creates an ID that clearly marks each new measurement run.
    This ID is appended to every result row.
    """
    try:
        stamp = SimpleDateFormat("yyyyMMdd_HHmmss").format(Date())
        return "Run_" + ascii_text(stamp)
    except:
        return "Run_unknown_time"


def get_image_title_ascii(imp):
    try:
        return ascii_text(imp.getTitle())
    except:
        return ""


def add_value(rt, heading, value):
    heading = ascii_text(heading)

    try:
        if value is None:
            rt.addValue(heading, "")
        else:
            rt.addValue(heading, value)
    except:
        try:
            rt.addValue(heading, ascii_text(value))
        except:
            pass


def add_nan(rt, heading):
    rt.addValue(ascii_text(heading), float("nan"))


def get_append_results_table(title):
    """
    Return an existing results table if it is already open.
    Otherwise create a new one.

    This lets repeated Analyze clicks append to the same named table.
    """
    title = ascii_text(title)

    try:
        rt = ResultsTable.getResultsTable(title)
        if rt is not None:
            return rt
    except:
        pass

    try:
        frame = WindowManager.getFrame(title)
        if frame is not None:
            try:
                tp = frame.getTextPanel()
                if tp is not None:
                    rt = tp.getResultsTable()
                    if rt is not None:
                        return rt
            except:
                pass
    except:
        pass

    return ResultsTable()


def append_rows_to_results_table(title, headers, rows):
    """
    Append new rows to a named ResultsTable window.
    """
    rt = get_append_results_table(title)

    for row in rows:
        rt.incrementCounter()

        for h in headers:
            value = ""
            try:
                value = row[h]
            except:
                value = ""

            add_value(rt, h, value)

    rt.show(title)
    return rt


def format_cell(value):
    if value is None:
        return ""

    if is_nan(value):
        return ""

    return ascii_text(value)


def escape_delimited_cell(value, delimiter):
    s = format_cell(value)
    s = s.replace("\r", " ")
    s = s.replace("\n", " ")

    if delimiter == ",":
        if "," in s or '"' in s:
            s = '"' + s.replace('"', '""') + '"'
        return s

    # TXT export is tab-delimited.
    s = s.replace("\t", " ")
    return s


def append_rows_to_file(file_path, headers, rows, delimiter):
    """
    Append rows to a CSV or TXT file.
    Writes the header only if the file is new or empty.
    """
    f = File(file_path)
    write_header = True

    try:
        if f.exists() and f.length() > 0:
            write_header = False
    except:
        write_header = True

    writer = None

    try:
        writer = BufferedWriter(FileWriter(f, True))

        if write_header:
            header_line = delimiter.join([escape_delimited_cell(h, delimiter) for h in headers])
            writer.write(header_line)
            writer.newLine()

        for row in rows:
            values = []

            for h in headers:
                try:
                    values.append(escape_delimited_cell(row[h], delimiter))
                except:
                    values.append("")

            writer.write(delimiter.join(values))
            writer.newLine()

        writer.flush()
        return True

    except Exception as e:
        IJ.log("Could not save table file:")
        IJ.log(ascii_text(file_path))
        IJ.log(ascii_text(e))
        return False

    finally:
        try:
            if writer is not None:
                writer.close()
        except:
            pass


def save_rows_to_disk(save_dir, table_title, headers, rows, save_csv, save_txt):
    """
    Save only the new measurement rows to CSV/TXT.
    Existing files are appended, not overwritten.
    """
    if save_dir is None or str(save_dir).strip() == "":
        return

    base = safe_title(table_title)

    if save_csv:
        try:
            csv_file = File(save_dir, base + ".csv").getPath()
            ok = append_rows_to_file(csv_file, headers, rows, ",")
            if ok:
                IJ.log("Saved/appended CSV: " + ascii_text(csv_file))
        except Exception as e:
            IJ.log("CSV save failed for " + ascii_text(table_title))
            IJ.log(ascii_text(e))

    if save_txt:
        try:
            txt_file = File(save_dir, base + ".txt").getPath()
            ok = append_rows_to_file(txt_file, headers, rows, "\t")
            if ok:
                IJ.log("Saved/appended TXT: " + ascii_text(txt_file))
        except Exception as e:
            IJ.log("TXT save failed for " + ascii_text(table_title))
            IJ.log(ascii_text(e))


def set_roi_manager_name(rm, one_based_index, roi, new_name):
    """
    Rename an ROI both in the ROI object and in the ROI Manager list.

    one_based_index is the index shown in the results table.
    ROI Manager API uses zero-based indexing internally.
    """
    new_name = ascii_text(new_name)
    zero_index = int(one_based_index) - 1

    try:
        roi.setName(new_name)
    except:
        pass

    renamed = False

    try:
        renamed = rm.rename(zero_index, new_name)
    except:
        renamed = False

    if not renamed:
        try:
            rm.select(zero_index)
            rm.runCommand("Rename", new_name)
            renamed = True
        except Exception as e:
            IJ.log("Could not rename ROI Manager entry " + str(one_based_index) + " to " + new_name)
            IJ.log(ascii_text(e))

    return renamed


# ============================================================
# ROI classification
# ============================================================

def is_line_roi(roi):
    """
    True for straight lines, segmented lines, freehand lines, and angle ROIs.
    """
    try:
        if roi.isLine():
            return True
    except:
        pass

    try:
        t = roi.getType()
        line_types = []

        for attr in ["LINE", "POLYLINE", "FREELINE", "ANGLE"]:
            try:
                line_types.append(getattr(Roi, attr))
            except:
                pass

        return t in line_types
    except:
        return False


def get_roi_points(roi):
    """
    Returns points from an ROI.

    For area ROIs: boundary points.
    For line ROIs: line path points.
    """
    fp = roi.getFloatPolygon()
    pts = []

    for i in range(fp.npoints):
        pts.append((float(fp.xpoints[i]), float(fp.ypoints[i])))

    # Remove duplicate closing point if present.
    if len(pts) > 1:
        x0, y0 = pts[0]
        x1, y1 = pts[-1]
        if abs(x0 - x1) < 1e-6 and abs(y0 - y1) < 1e-6:
            pts = pts[:-1]

    return pts


def is_mito_roi(roi):
    """
    Every non-line closed/area ROI is treated as a mitochondrion.

    This includes polygon, freehand, rectangle, oval, traced area ROIs, etc.,
    as long as ImageJ can provide at least 3 outline points.
    """
    if is_line_roi(roi):
        return False

    try:
        pts = get_roi_points(roi)
        return pts is not None and len(pts) >= 3
    except:
        return False


def parse_roi_manager():
    rm = get_rm()
    rois = rm.getRoisAsArray()

    mitos = []
    lines = []
    other = []
    warnings = []

    for i in range(len(rois)):
        roi = rois[i]

        try:
            pts = get_roi_points(roi)
        except:
            pts = []

        if is_line_roi(roi):
            name = safe_name(roi, "line_" + str(i + 1))

            if len(pts) < 2:
                warnings.append(name + " is a line ROI but has fewer than 2 points.")
            else:
                lines.append({
                    "index": i + 1,
                    "name": name,
                    "roi": roi,
                    "pts": pts
                })

        elif is_mito_roi(roi):
            name = safe_name(roi, "area_" + str(i + 1))

            mitos.append({
                "index": i + 1,
                "name": name,
                "roi": roi,
                "pts": pts
            })

        else:
            name = safe_name(roi, "ROI_" + str(i + 1))
            other.append({
                "index": i + 1,
                "name": name,
                "roi": roi,
                "pts": pts
            })

    return mitos, lines, other, warnings


# ============================================================
# Geometry helpers
# ============================================================

def to_phys(p, cal):
    return (p[0] * cal.pixelWidth, p[1] * cal.pixelHeight)


def dist_phys(p, q, cal):
    pp = to_phys(p, cal)
    qq = to_phys(q, cal)

    dx = pp[0] - qq[0]
    dy = pp[1] - qq[1]

    return math.sqrt(dx * dx + dy * dy)


def polyline_length(pts, cal):
    if pts is None or len(pts) < 2:
        return 0.0

    total = 0.0

    for i in range(len(pts) - 1):
        total += dist_phys(pts[i], pts[i + 1], cal)

    return total


def polygon_edges(poly):
    edges = []
    n = len(poly)

    if n < 2:
        return edges

    for i in range(n):
        edges.append((poly[i], poly[(i + 1) % n]))

    return edges


def line_segments(pts):
    segs = []

    if pts is None or len(pts) < 2:
        return segs

    for i in range(len(pts) - 1):
        segs.append((pts[i], pts[i + 1]))

    return segs


def orientation(a, b, c):
    """
    Signed orientation of triangle abc in pixel coordinates.
    """
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def point_on_segment(p, a, b, eps):
    cross = orientation(a, b, p)

    if abs(cross) > eps:
        return False

    minx = min(a[0], b[0]) - eps
    maxx = max(a[0], b[0]) + eps
    miny = min(a[1], b[1]) - eps
    maxy = max(a[1], b[1]) + eps

    return p[0] >= minx and p[0] <= maxx and p[1] >= miny and p[1] <= maxy


def segments_intersect(a, b, c, d):
    eps = 1e-7

    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)

    if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and \
       ((o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)):
        return True

    if abs(o1) <= eps and point_on_segment(c, a, b, eps):
        return True
    if abs(o2) <= eps and point_on_segment(d, a, b, eps):
        return True
    if abs(o3) <= eps and point_on_segment(a, c, d, eps):
        return True
    if abs(o4) <= eps and point_on_segment(b, c, d, eps):
        return True

    return False


def point_to_segment_distance(p, a, b, cal):
    """
    Calibrated distance from point p to segment ab.
    Projection is done in physical XY coordinates.
    """
    px, py = to_phys(p, cal)
    ax, ay = to_phys(a, cal)
    bx, by = to_phys(b, cal)

    vx = bx - ax
    vy = by - ay
    wx = px - ax
    wy = py - ay

    vv = vx * vx + vy * vy

    if vv <= 1e-12:
        dx = px - ax
        dy = py - ay
        return math.sqrt(dx * dx + dy * dy)

    t = (wx * vx + wy * vy) / vv

    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0

    cx = ax + t * vx
    cy = ay + t * vy

    dx = px - cx
    dy = py - cy

    return math.sqrt(dx * dx + dy * dy)


def segment_to_segment_distance(a, b, c, d, cal):
    if segments_intersect(a, b, c, d):
        return 0.0

    d1 = point_to_segment_distance(a, c, d, cal)
    d2 = point_to_segment_distance(b, c, d, cal)
    d3 = point_to_segment_distance(c, a, b, cal)
    d4 = point_to_segment_distance(d, a, b, cal)

    return min(d1, d2, d3, d4)


def point_to_polygon_boundary_distance(p, poly_pts, cal):
    edges = polygon_edges(poly_pts)

    if len(edges) == 0:
        return float("nan")

    best = None

    for a, b in edges:
        dd = point_to_segment_distance(p, a, b, cal)

        if best is None or dd < best:
            best = dd

    if best is None:
        return float("nan")

    return best


def line_to_polygon_min_boundary_distance(line_pts, poly_pts, cal):
    segs_l = line_segments(line_pts)
    edges_p = polygon_edges(poly_pts)

    if len(segs_l) == 0 or len(edges_p) == 0:
        return float("nan")

    best = None

    for a, b in segs_l:
        for c, d in edges_p:
            dd = segment_to_segment_distance(a, b, c, d, cal)

            if best is None or dd < best:
                best = dd

    if best is None:
        return float("nan")

    return best


def point_to_polyline_distance(p, line_pts, cal):
    segs = line_segments(line_pts)

    if len(segs) == 0:
        return float("nan")

    best = None

    for a, b in segs:
        dd = point_to_segment_distance(p, a, b, cal)

        if best is None or dd < best:
            best = dd

    if best is None:
        return float("nan")

    return best


def polyline_to_polyline_min_distance(line_a, line_b, cal):
    segs_a = line_segments(line_a)
    segs_b = line_segments(line_b)

    if len(segs_a) == 0 or len(segs_b) == 0:
        return float("nan")

    best = None

    for a, b in segs_a:
        for c, d in segs_b:
            dd = segment_to_segment_distance(a, b, c, d, cal)

            if best is None or dd < best:
                best = dd

    if best is None:
        return float("nan")

    return best


# ============================================================
# Polygon containment and line sampling
# ============================================================

def point_in_polygon(p, poly):
    """
    Ray-casting point-in-polygon.
    Boundary counts as inside.
    """
    n = len(poly)

    if n < 3:
        return False

    eps = 1e-7

    for a, b in polygon_edges(poly):
        if point_on_segment(p, a, b, eps):
            return True

    x, y = p
    inside = False
    j = n - 1

    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]

        crosses = (yi > y) != (yj > y)

        if crosses:
            x_intersect = (xj - xi) * (y - yi) / (yj - yi) + xi

            if x < x_intersect:
                inside = not inside

        j = i

    return inside


def sample_polyline_points(pts, spacing_px):
    samples = []

    if pts is None or len(pts) == 0:
        return samples

    if len(pts) == 1:
        return [pts[0]]

    for i in range(len(pts) - 1):
        a = pts[i]
        b = pts[i + 1]

        dx = b[0] - a[0]
        dy = b[1] - a[1]

        length_px = math.sqrt(dx * dx + dy * dy)
        steps = int(math.ceil(length_px / spacing_px))

        if steps < 1:
            steps = 1

        for s in range(steps + 1):
            if i > 0 and s == 0:
                continue

            t = float(s) / float(steps)

            x = a[0] + t * dx
            y = a[1] + t * dy

            samples.append((x, y))

    return samples


def line_polygon_relation(line_pts, poly_pts):
    """
    Returns:
      inside       - all sampled line points are inside or on the mito boundary
      outside      - all sampled line points are outside and no crossing is detected
      intersecting - line touches/crosses boundary or is partly inside
      invalid      - bad geometry

    Boundary points count as inside. This helps classify cristae whose
    endpoints touch the mitochondrial membrane as internal cristae.
    """
    if line_pts is None or len(line_pts) < 2 or poly_pts is None or len(poly_pts) < 3:
        return "invalid"

    samples = sample_polyline_points(line_pts, SAMPLE_SPACING_PX)

    if len(samples) == 0:
        return "invalid"

    inside_count = 0

    for p in samples:
        if point_in_polygon(p, poly_pts):
            inside_count += 1

    all_inside = inside_count == len(samples)
    any_inside = inside_count > 0

    crosses_boundary = False

    for a, b in line_segments(line_pts):
        for c, d in polygon_edges(poly_pts):
            if segments_intersect(a, b, c, d):
                crosses_boundary = True
                break

        if crosses_boundary:
            break

    if all_inside:
        return "inside"

    if any_inside or crosses_boundary:
        return "intersecting"

    return "outside"


def sampled_line_to_polygon_boundary_stats(line_pts, poly_pts, cal):
    """
    Mean/min/max distance from sampled ER points to the closest mito boundary.
    Used only for ER-to-closest-mito reporting.
    """
    samples = sample_polyline_points(line_pts, SAMPLE_SPACING_PX)
    values = []

    for p in samples:
        dd = point_to_polygon_boundary_distance(p, poly_pts, cal)

        if not is_nan(dd):
            values.append(dd)

    if len(values) == 0:
        return (float("nan"), float("nan"), float("nan"))

    return (sum(values) / len(values), min(values), max(values))


def sampled_line_to_line_stats(line_a, line_b, cal):
    """
    Symmetric sampled centerline-to-centerline distance between two cristae.

    Returns:
      average distance
      minimum sampled distance
      maximum sampled distance
    """
    vals = []

    samples_a = sample_polyline_points(line_a, SAMPLE_SPACING_PX)
    samples_b = sample_polyline_points(line_b, SAMPLE_SPACING_PX)

    for p in samples_a:
        dd = point_to_polyline_distance(p, line_b, cal)

        if not is_nan(dd):
            vals.append(dd)

    for p in samples_b:
        dd = point_to_polyline_distance(p, line_a, cal)

        if not is_nan(dd):
            vals.append(dd)

    if len(vals) == 0:
        return (float("nan"), float("nan"), float("nan"))

    return (sum(vals) / len(vals), min(vals), max(vals))


# ============================================================
# Mito shape measurements
# ============================================================

def polygon_area(poly_pts, cal):
    n = len(poly_pts)

    if n < 3:
        return 0.0

    area2 = 0.0

    for i in range(n):
        x1, y1 = to_phys(poly_pts[i], cal)
        x2, y2 = to_phys(poly_pts[(i + 1) % n], cal)

        area2 += x1 * y2 - x2 * y1

    return abs(area2) / 2.0


def polygon_perimeter(poly_pts, cal):
    n = len(poly_pts)

    if n < 2:
        return 0.0

    total = 0.0

    for i in range(n):
        total += dist_phys(poly_pts[i], poly_pts[(i + 1) % n], cal)

    return total


def convex_hull(points):
    """
    Monotonic chain convex hull.
    Points must be physical-coordinate tuples.
    """
    pts = sorted(list(set(points)))

    if len(pts) <= 1:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []

    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()

        lower.append(p)

    upper = []

    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()

        upper.append(p)

    return lower[:-1] + upper[:-1]


def feret_length_width(poly_pts, cal):
    """
    Approximate Feret length and Feret width from the convex hull.

    Feret length:
      maximum distance between hull points

    Feret width:
      minimum caliper width over hull edge orientations
    """
    phys_pts = []

    for p in poly_pts:
        phys_pts.append(to_phys(p, cal))

    hull = convex_hull(phys_pts)
    n = len(hull)

    if n < 2:
        return (0.0, 0.0)

    max_d = 0.0

    for i in range(n):
        for j in range(i + 1, n):
            dx = hull[i][0] - hull[j][0]
            dy = hull[i][1] - hull[j][1]

            dd = math.sqrt(dx * dx + dy * dy)

            if dd > max_d:
                max_d = dd

    min_width = None

    for i in range(n):
        p1 = hull[i]
        p2 = hull[(i + 1) % n]

        ex = p2[0] - p1[0]
        ey = p2[1] - p1[1]

        elen = math.sqrt(ex * ex + ey * ey)

        if elen <= 1e-12:
            continue

        nx = -ey / elen
        ny = ex / elen

        projections = []

        for p in hull:
            projections.append(p[0] * nx + p[1] * ny)

        width = max(projections) - min(projections)

        if min_width is None or width < min_width:
            min_width = width

    if min_width is None:
        min_width = 0.0

    return (max_d, min_width)


def mito_metrics(mito, cal):
    pts = mito["pts"]

    area = polygon_area(pts, cal)
    perimeter = polygon_perimeter(pts, cal)

    if perimeter > 0:
        circularity = 4.0 * math.pi * area / (perimeter * perimeter)
    else:
        circularity = float("nan")

    feret_len, feret_width = feret_length_width(pts, cal)

    if feret_width > 0:
        aspect_ratio = feret_len / feret_width
    else:
        aspect_ratio = float("nan")

    if area > 0:
        equiv_diameter = math.sqrt(4.0 * area / math.pi)
    else:
        equiv_diameter = float("nan")

    return {
        "area": area,
        "perimeter": perimeter,
        "circularity": circularity,
        "feret_length": feret_len,
        "feret_width": feret_width,
        "aspect_ratio": aspect_ratio,
        "equiv_diameter": equiv_diameter
    }


# ============================================================
# Assignment and renaming
# ============================================================

def relation_priority(relation):
    if relation == "inside":
        return 0
    if relation == "intersecting":
        return 1
    if relation == "outside":
        return 2
    return 3


def assign_lines_to_mitos(lines, mitos, cal):
    """
    Assign every ROI line to the most relevant mito.

    Inside lines become cristae.
    Outside or intersecting lines become ER.

    Distances to closest mito are calculated here for ER reporting only.
    Crista-to-mito distances are not reported.
    """
    for line in lines:
        best = None

        for mito in mitos:
            relation = line_polygon_relation(line["pts"], mito["pts"])

            min_exact = line_to_polygon_min_boundary_distance(
                line["pts"],
                mito["pts"],
                cal
            )

            av_d, sample_min_d, max_d = sampled_line_to_polygon_boundary_stats(
                line["pts"],
                mito["pts"],
                cal
            )

            candidate = {
                "mito": mito,
                "relation": relation,
                "min": min_exact,
                "av": av_d,
                "max": max_d,
                "sample_min": sample_min_d
            }

            if best is None:
                best = candidate
            else:
                old_key = (
                    relation_priority(best["relation"]),
                    safe_number_for_sort(best["min"])
                )
                new_key = (
                    relation_priority(candidate["relation"]),
                    safe_number_for_sort(candidate["min"])
                )

                if new_key < old_key:
                    best = candidate

        if best is None:
            line["assigned_mito"] = None
            line["relationship"] = "unassigned"
            line["roi_type"] = "ER"
            line["dist_to_closest_mito_min"] = float("nan")
            line["dist_to_closest_mito_av"] = float("nan")
            line["dist_to_closest_mito_max"] = float("nan")
        else:
            line["assigned_mito"] = best["mito"]
            line["relationship"] = best["relation"]

            if best["relation"] == "inside":
                line["roi_type"] = "Cris"
            else:
                line["roi_type"] = "ER"

            line["dist_to_closest_mito_min"] = best["min"]
            line["dist_to_closest_mito_av"] = best["av"]
            line["dist_to_closest_mito_max"] = best["max"]


def prepare_rois_for_analysis(cal, rename_rois):
    """
    Parse, assign, and optionally rename ROI Manager entries.

    Closed/non-line ROIs:
      Mito_1, Mito_2, ...

    Lines inside a mito:
      Cris_1-Mito_1, Cris_2-Mito_1, Cris_1-Mito_2, ...

    Lines outside/intersecting mitos:
      ER_1, ER_2, ...
    """
    rm = get_rm()
    mitos, lines, other, warnings = parse_roi_manager()

    if rename_rois:
        for i in range(len(mitos)):
            new_name = "Mito_" + str(i + 1)
            mitos[i]["name"] = new_name
            set_roi_manager_name(rm, mitos[i]["index"], mitos[i]["roi"], new_name)

    if len(mitos) > 0 and len(lines) > 0:
        assign_lines_to_mitos(lines, mitos, cal)

    if rename_rois and len(lines) > 0:
        cris_counts = {}
        er_count = 0

        for mito in mitos:
            cris_counts[mito["name"]] = 0

        for line in lines:
            if line.get("roi_type") == "Cris" and line.get("assigned_mito") is not None:
                mito_name = line["assigned_mito"]["name"]
                cris_counts[mito_name] = cris_counts[mito_name] + 1
                new_name = "Cris_" + str(cris_counts[mito_name]) + "-" + mito_name
            else:
                er_count = er_count + 1
                new_name = "ER_" + str(er_count)

            line["name"] = new_name
            set_roi_manager_name(rm, line["index"], line["roi"], new_name)

    return mitos, lines, other, warnings


# ============================================================
# Distance-map QA helpers
# ============================================================

def burn_polyline(ip, pts, closed, line_width):
    if pts is None or len(pts) < 2:
        return

    ip.setColor(0)
    ip.setLineWidth(line_width)

    for i in range(len(pts) - 1):
        x1 = int(round(pts[i][0]))
        y1 = int(round(pts[i][1]))
        x2 = int(round(pts[i + 1][0]))
        y2 = int(round(pts[i + 1][1]))

        ip.drawLine(x1, y1, x2, y2)

    if closed and len(pts) >= 3:
        x1 = int(round(pts[-1][0]))
        y1 = int(round(pts[-1][1]))
        x2 = int(round(pts[0][0]))
        y2 = int(round(pts[0][1]))

        ip.drawLine(x1, y1, x2, y2)


def make_float_edm_from_black_pixels(ip, cal):
    edm_plugin = EDM()
    float_ip = edm_plugin.makeFloatEDM(ip, 0, False)

    # EDM itself is pixel-based. If XY pixels are isotropic, scale display
    # values to physical units for easier visual inspection.
    try:
        if abs(cal.pixelWidth - cal.pixelHeight) < 1e-12:
            float_ip.multiply(cal.pixelWidth)
    except:
        pass

    return float_ip


def copy_calibration(dst_imp, cal):
    try:
        dst_imp.setCalibration(cal.copy())
    except:
        try:
            dst_imp.setCalibration(cal)
        except:
            pass


def clone_roi_with_color(roi, color):
    try:
        r = roi.clone()
    except:
        r = roi

    try:
        r.setStrokeColor(color)
    except:
        pass

    return r


def show_er_to_mito_distance_map(source_imp, mito, er_roi, cal):
    """
    Visual QA map for ER-to-closest-mito distance.

    Black source object:
      mito boundary

    Map values:
      distance to the closest mito boundary

    Overlay:
      mito and ER
    """
    width = source_imp.getWidth()
    height = source_imp.getHeight()

    ip = ByteProcessor(width, height)
    ip.setValue(255)
    ip.fill()

    burn_polyline(ip, mito["pts"], True, 1)

    float_ip = make_float_edm_from_black_pixels(ip, cal)

    title = safe_title("DistanceMap_ER_to_ClosestMitochondrion_" + er_roi["name"] + "_to_" + mito["name"])
    edm_imp = ImagePlus(title, float_ip)
    copy_calibration(edm_imp, cal)

    overlay = Overlay()
    overlay.add(clone_roi_with_color(mito["roi"], Color.green))
    overlay.add(clone_roi_with_color(er_roi["roi"], Color.cyan))
    edm_imp.setOverlay(overlay)

    edm_imp.show()

    try:
        IJ.run(edm_imp, "Fire", "")
    except:
        pass

    try:
        IJ.resetMinAndMax(edm_imp)
    except:
        pass


def show_crista_to_crista_distance_map(source_imp, base_crista, target_crista, cal):
    """
    Visual QA map for crista-to-crista distance.

    Black source object:
      base crista

    Map values:
      distance to the base crista

    Overlay:
      base crista and target crista
    """
    width = source_imp.getWidth()
    height = source_imp.getHeight()

    ip = ByteProcessor(width, height)
    ip.setValue(255)
    ip.fill()

    burn_polyline(ip, base_crista["pts"], False, 1)

    float_ip = make_float_edm_from_black_pixels(ip, cal)

    title = safe_title("DistanceMap_Crista_to_Crista_" + base_crista["name"] + "_to_" + target_crista["name"])
    edm_imp = ImagePlus(title, float_ip)
    copy_calibration(edm_imp, cal)

    overlay = Overlay()
    overlay.add(clone_roi_with_color(base_crista["roi"], Color.yellow))
    overlay.add(clone_roi_with_color(target_crista["roi"], Color.magenta))
    edm_imp.setOverlay(overlay)

    edm_imp.show()

    try:
        IJ.run(edm_imp, "Fire", "")
    except:
        pass

    try:
        IJ.resetMinAndMax(edm_imp)
    except:
        pass


# ============================================================
# Main analysis
# ============================================================

def run_analysis(show_maps, save_csv, save_txt, save_dir):
    IJ.log("Mito/Cristae/ER tool: run_analysis started.")

    imp = get_current_image()

    if imp is None:
        IJ.showMessage("Please open an image first.")
        IJ.log("Mito/Cristae/ER tool: no image open.")
        return

    cal = imp.getCalibration()
    unit = ascii_unit(cal.getUnit())

    measurement_set = make_measurement_set_id()
    image_title = get_image_title_ascii(imp)

    mitos, lines, other, warnings = prepare_rois_for_analysis(cal, True)

    IJ.log("Measurement set: " + measurement_set)
    IJ.log("ROI Manager parsed and renamed:")
    IJ.log("  Mito/area ROIs: " + str(len(mitos)))
    IJ.log("  ROI lines: " + str(len(lines)))
    IJ.log("  Other ignored ROIs: " + str(len(other)))

    if len(warnings) > 0:
        IJ.log("Warnings:")
        for w in warnings:
            IJ.log("  - " + ascii_text(w))

    if len(mitos) == 0:
        IJ.showMessage("No mito area ROIs found.\nAdd polygon/freehand/area ROIs to the ROI Manager.")
        return

    if len(lines) == 0:
        IJ.showMessage("No ROI lines found.\nAdd line/freehand-line/polyline ROIs to the ROI Manager.")
        return

    map_count = 0

    # ------------------------------------------------------------
    # Table 1: Mitochondria morphology
    # ROI Manager Index is intentionally last.
    # ------------------------------------------------------------

    mito_headers = [
        "Measurement Set",
        "Image",
        "Mitochondrion",
        "Area (" + unit + "^2)",
        "Perimeter (" + unit + ")",
        "Feret Length (" + unit + ")",
        "Feret Width (" + unit + ")",
        "Aspect Ratio",
        "Circularity",
        "Equiv Diameter (" + unit + ")",
        "ROI Manager Index"
    ]

    mito_rows = []

    for mito in mitos:
        m = mito_metrics(mito, cal)

        row = {}
        row["Measurement Set"] = measurement_set
        row["Image"] = image_title
        row["Mitochondrion"] = mito["name"]
        row["Area (" + unit + "^2)"] = m["area"]
        row["Perimeter (" + unit + ")"] = m["perimeter"]
        row["Feret Length (" + unit + ")"] = m["feret_length"]
        row["Feret Width (" + unit + ")"] = m["feret_width"]
        row["Aspect Ratio"] = m["aspect_ratio"]
        row["Circularity"] = m["circularity"]
        row["Equiv Diameter (" + unit + ")"] = m["equiv_diameter"]
        row["ROI Manager Index"] = mito["index"]

        mito_rows.append(row)

    append_rows_to_results_table(TABLE_MITO, mito_headers, mito_rows)
    save_rows_to_disk(save_dir, TABLE_MITO, mito_headers, mito_rows, save_csv, save_txt)
    IJ.log(TABLE_MITO + " table appended.")

    # ------------------------------------------------------------
    # Table 2: ER to closest mitochondrion
    # Crista-to-mito distances are intentionally not reported.
    # Relationship is second-to-last.
    # ROI Manager Index is last.
    # ------------------------------------------------------------

    er_headers = [
        "Measurement Set",
        "Image",
        "ER",
        "ER Length (" + unit + ")",
        "Closest Mitochondrion",
        "Dist to Closest Mito Min (" + unit + ")",
        "Dist to Closest Mito Av (" + unit + ")",
        "Dist to Closest Mito Max (" + unit + ")",
        "Relationship",
        "ROI Manager Index"
    ]

    er_rows = []

    internal_by_mito = {}

    for mito in mitos:
        internal_by_mito[mito["name"]] = []

    for line in lines:
        assigned_mito = line.get("assigned_mito")

        if line.get("roi_type") == "Cris" and assigned_mito is not None:
            internal_by_mito[assigned_mito["name"]].append(line)
            continue

        row = {}
        row["Measurement Set"] = measurement_set
        row["Image"] = image_title
        row["ER"] = line["name"]
        row["ER Length (" + unit + ")"] = polyline_length(line["pts"], cal)

        if assigned_mito is not None:
            row["Closest Mitochondrion"] = assigned_mito["name"]
        else:
            row["Closest Mitochondrion"] = ""

        row["Dist to Closest Mito Min (" + unit + ")"] = line.get("dist_to_closest_mito_min")
        row["Dist to Closest Mito Av (" + unit + ")"] = line.get("dist_to_closest_mito_av")
        row["Dist to Closest Mito Max (" + unit + ")"] = line.get("dist_to_closest_mito_max")
        row["Relationship"] = line.get("relationship", "")
        row["ROI Manager Index"] = line["index"]

        er_rows.append(row)

        if show_maps and assigned_mito is not None and map_count < MAX_DISTANCE_MAPS:
            show_er_to_mito_distance_map(imp, assigned_mito, line, cal)
            map_count = map_count + 1

    if len(er_rows) == 0:
        row = {}
        row["Measurement Set"] = measurement_set
        row["Image"] = image_title
        row["ER"] = "No ER ROIs"
        row["ER Length (" + unit + ")"] = ""
        row["Closest Mitochondrion"] = ""
        row["Dist to Closest Mito Min (" + unit + ")"] = ""
        row["Dist to Closest Mito Av (" + unit + ")"] = ""
        row["Dist to Closest Mito Max (" + unit + ")"] = ""
        row["Relationship"] = ""
        row["ROI Manager Index"] = ""
        er_rows.append(row)

    append_rows_to_results_table(TABLE_ER, er_headers, er_rows)
    save_rows_to_disk(save_dir, TABLE_ER, er_headers, er_rows, save_csv, save_txt)
    IJ.log(TABLE_ER + " table appended.")

    # ------------------------------------------------------------
    # Table 3: Crista-to-crista nearest-neighbor distances.
    # NN = Nearest Neighbor.
    # Both NN1 and NN2 are kept.
    # No "line" wording in column headers.
    # ------------------------------------------------------------

    cristae_headers = [
        "Measurement Set",
        "Image",
        "Mitochondrion",
        "Crista",
        "Crista Length (" + unit + ")",
        "Cristae Count in Mito",
        "NN1 Crista",
        "NN1 Dist Min (" + unit + ")",
        "NN1 Dist Av (" + unit + ")",
        "NN1 Dist Max (" + unit + ")",
        "NN2 Crista",
        "NN2 Dist Min (" + unit + ")",
        "NN2 Dist Av (" + unit + ")",
        "NN2 Dist Max (" + unit + ")",
        "ROI Manager Index"
    ]

    cristae_rows = []
    shown_cristae_map_pairs = set()

    for mito in mitos:
        mito_name = mito["name"]
        members = internal_by_mito[mito_name]

        for line in members:
            distances = []

            for other_line in members:
                if other_line["index"] == line["index"]:
                    continue

                av_dist, sampled_min_dist, max_dist = sampled_line_to_line_stats(
                    line["pts"],
                    other_line["pts"],
                    cal
                )

                exact_min_dist = polyline_to_polyline_min_distance(
                    line["pts"],
                    other_line["pts"],
                    cal
                )

                distances.append({
                    "crista": other_line,
                    "av": av_dist,
                    "min": exact_min_dist,
                    "max": max_dist
                })

            if RANK_CRISTAE_BY_AVERAGE_DISTANCE:
                distances.sort(key=lambda x: safe_number_for_sort(x["av"]))
            else:
                distances.sort(key=lambda x: safe_number_for_sort(x["min"]))

            row = {}
            row["Measurement Set"] = measurement_set
            row["Image"] = image_title
            row["Mitochondrion"] = mito_name
            row["Crista"] = line["name"]
            row["Crista Length (" + unit + ")"] = polyline_length(line["pts"], cal)
            row["Cristae Count in Mito"] = len(members)
            row["ROI Manager Index"] = line["index"]

            if len(distances) >= 1:
                nn1 = distances[0]

                row["NN1 Crista"] = nn1["crista"]["name"]
                row["NN1 Dist Min (" + unit + ")"] = nn1["min"]
                row["NN1 Dist Av (" + unit + ")"] = nn1["av"]
                row["NN1 Dist Max (" + unit + ")"] = nn1["max"]

                if show_maps and map_count < MAX_DISTANCE_MAPS:
                    a = min(line["index"], nn1["crista"]["index"])
                    b = max(line["index"], nn1["crista"]["index"])
                    key = mito_name + "_NN1_" + str(a) + "_" + str(b)

                    if key not in shown_cristae_map_pairs:
                        show_crista_to_crista_distance_map(imp, line, nn1["crista"], cal)
                        shown_cristae_map_pairs.add(key)
                        map_count = map_count + 1
            else:
                row["NN1 Crista"] = ""
                row["NN1 Dist Min (" + unit + ")"] = ""
                row["NN1 Dist Av (" + unit + ")"] = ""
                row["NN1 Dist Max (" + unit + ")"] = ""

            if len(distances) >= 2:
                nn2 = distances[1]

                row["NN2 Crista"] = nn2["crista"]["name"]
                row["NN2 Dist Min (" + unit + ")"] = nn2["min"]
                row["NN2 Dist Av (" + unit + ")"] = nn2["av"]
                row["NN2 Dist Max (" + unit + ")"] = nn2["max"]

                if show_maps and map_count < MAX_DISTANCE_MAPS:
                    a = min(line["index"], nn2["crista"]["index"])
                    b = max(line["index"], nn2["crista"]["index"])
                    key = mito_name + "_NN2_" + str(a) + "_" + str(b)

                    if key not in shown_cristae_map_pairs:
                        show_crista_to_crista_distance_map(imp, line, nn2["crista"], cal)
                        shown_cristae_map_pairs.add(key)
                        map_count = map_count + 1
            else:
                row["NN2 Crista"] = ""
                row["NN2 Dist Min (" + unit + ")"] = ""
                row["NN2 Dist Av (" + unit + ")"] = ""
                row["NN2 Dist Max (" + unit + ")"] = ""

            cristae_rows.append(row)

    if len(cristae_rows) == 0:
        row = {}
        row["Measurement Set"] = measurement_set
        row["Image"] = image_title
        row["Mitochondrion"] = ""
        row["Crista"] = "No crista ROIs"
        row["Crista Length (" + unit + ")"] = ""
        row["Cristae Count in Mito"] = ""
        row["NN1 Crista"] = ""
        row["NN1 Dist Min (" + unit + ")"] = ""
        row["NN1 Dist Av (" + unit + ")"] = ""
        row["NN1 Dist Max (" + unit + ")"] = ""
        row["NN2 Crista"] = ""
        row["NN2 Dist Min (" + unit + ")"] = ""
        row["NN2 Dist Av (" + unit + ")"] = ""
        row["NN2 Dist Max (" + unit + ")"] = ""
        row["ROI Manager Index"] = ""
        cristae_rows.append(row)

    append_rows_to_results_table(TABLE_CRISTAE, cristae_headers, cristae_rows)
    save_rows_to_disk(save_dir, TABLE_CRISTAE, cristae_headers, cristae_rows, save_csv, save_txt)
    IJ.log(TABLE_CRISTAE + " table appended.")

    if show_maps:
        IJ.log("Distance-map QA windows shown: " + str(map_count))

        if map_count >= MAX_DISTANCE_MAPS:
            IJ.log("Distance-map QA stopped at MAX_DISTANCE_MAPS = " + str(MAX_DISTANCE_MAPS))

    IJ.log("Mito/Cristae/ER analysis complete.")
    IJ.log("Measurement set completed: " + measurement_set)

    try:
        IJ.selectWindow(imp.getTitle())
    except:
        pass


# ============================================================
# GUI
# ============================================================

class MitoCristaeDistanceTool(JFrame):

    def __init__(self):
        super(MitoCristaeDistanceTool, self).__init__("Mito / Cristae / ER Distance")

        self.setName("MitoCristaeDistanceToolFrame")
        self.setSize(900, 270)
        self.setLayout(BoxLayout(self.getContentPane(), BoxLayout.Y_AXIS))

        self.show_mitos = True
        self.show_lines = True
        self.save_dir = None

        info = JLabel("Area ROIs -> Mito_#. Internal lines -> Cris_#-Mito_#. Other lines -> ER_#.")

        p0 = JPanel(FlowLayout(FlowLayout.CENTER))
        p0.add(info)

        self.cb_maps = JCheckBox("Show QA distance maps", False)

        p_maps = JPanel(FlowLayout(FlowLayout.CENTER))
        p_maps.add(self.cb_maps)

        self.cb_save_csv = JCheckBox("Save CSV", False)
        self.cb_save_txt = JCheckBox("Save TXT", False)
        btn_choose_folder = JButton("Choose Save Folder", actionPerformed=self.choose_save_folder)
        self.lbl_save_folder = JLabel("Save folder: not selected")

        p_save1 = JPanel(FlowLayout(FlowLayout.CENTER))
        p_save1.add(self.cb_save_csv)
        p_save1.add(self.cb_save_txt)
        p_save1.add(btn_choose_folder)

        p_save2 = JPanel(FlowLayout(FlowLayout.CENTER))
        p_save2.add(self.lbl_save_folder)

        btn_check = JButton("Check + Rename ROIs", actionPerformed=self.check_rois)
        btn_analyze = JButton("Analyze", actionPerformed=self.analyze)

        p1 = JPanel(FlowLayout(FlowLayout.CENTER))
        p1.add(btn_check)
        p1.add(btn_analyze)

        self.btn_toggle_mitos = JButton("Hide Mitos", actionPerformed=self.toggle_mitos)
        self.btn_toggle_lines = JButton("Hide Lines", actionPerformed=self.toggle_lines)

        btn_show_all = JButton("Show All", actionPerformed=self.show_all)
        btn_hide_all = JButton("Hide All", actionPerformed=self.hide_all)
        btn_clear = JButton("Clear ROIs", actionPerformed=self.clear_rois)

        p2 = JPanel(FlowLayout(FlowLayout.CENTER))
        p2.add(self.btn_toggle_mitos)
        p2.add(self.btn_toggle_lines)
        p2.add(btn_show_all)
        p2.add(btn_hide_all)
        p2.add(btn_clear)

        self.add(p0)
        self.add(p_maps)
        self.add(p_save1)
        self.add(p_save2)
        self.add(p1)
        self.add(p2)

        self.setAlwaysOnTop(True)
        self.setLocationRelativeTo(None)
        self.setVisible(True)

    def choose_save_folder(self, event):
        try:
            dc = DirectoryChooser("Choose folder for saved tables")
            directory = dc.getDirectory()

            if directory is not None and str(directory).strip() != "":
                self.save_dir = directory
                self.lbl_save_folder.setText("Save folder: " + ascii_text(directory))
                IJ.log("Save folder set to: " + ascii_text(directory))
        except Exception as e:
            IJ.log("Could not choose save folder:")
            IJ.log(ascii_text(e))
            IJ.showMessage("Save Folder Error", ascii_text(e))

    def ensure_save_folder_if_needed(self):
        save_csv = self.cb_save_csv.isSelected()
        save_txt = self.cb_save_txt.isSelected()

        if not save_csv and not save_txt:
            return None

        if self.save_dir is not None and str(self.save_dir).strip() != "":
            return self.save_dir

        try:
            dc = DirectoryChooser("Choose folder for saved tables")
            directory = dc.getDirectory()

            if directory is not None and str(directory).strip() != "":
                self.save_dir = directory
                self.lbl_save_folder.setText("Save folder: " + ascii_text(directory))
                IJ.log("Save folder set to: " + ascii_text(directory))
                return self.save_dir
        except Exception as e:
            IJ.log("Could not choose save folder:")
            IJ.log(ascii_text(e))

        IJ.showMessage("No save folder selected", "Tables will be shown and appended in ImageJ, but not saved to disk.")
        return None

    def refresh_overlay(self):
        imp = get_current_image()

        if imp is None:
            return

        rm = get_rm()

        try:
            rm.runCommand(imp, "Show None")
        except:
            try:
                rm.runCommand("Show None")
            except:
                pass

        mitos, lines, other, warnings = parse_roi_manager()

        overlay = Overlay()

        if self.show_mitos:
            for mito in mitos:
                try:
                    r = mito["roi"].clone()
                except:
                    r = mito["roi"]

                if USE_COLORED_OVERLAY:
                    try:
                        r.setStrokeColor(Color.green)
                    except:
                        pass

                overlay.add(r)

        if self.show_lines:
            for line in lines:
                try:
                    r = line["roi"].clone()
                except:
                    r = line["roi"]

                if USE_COLORED_OVERLAY:
                    try:
                        r.setStrokeColor(Color.cyan)
                    except:
                        pass

                overlay.add(r)

        imp.setOverlay(overlay)
        imp.updateAndDraw()

    def check_rois(self, event):
        IJ.log("Mito/Cristae/ER tool: Check + Rename ROIs clicked.")

        try:
            imp = get_current_image()

            if imp is None:
                IJ.showMessage("Please open an image first.")
                return

            cal = imp.getCalibration()
            mitos, lines, other, warnings = prepare_rois_for_analysis(cal, True)

            msg = ""
            msg += "ROIs were checked and renamed.\n\n"
            msg += "Mito/area ROIs found: " + str(len(mitos)) + "\n"
            msg += "ROI lines found: " + str(len(lines)) + "\n"
            msg += "Other ignored ROIs: " + str(len(other)) + "\n\n"

            if len(mitos) > 0:
                msg += "Mitochondria:\n"
                for mito in mitos:
                    msg += "  - " + ascii_text(mito["name"]) + "\n"
                msg += "\n"

            if len(lines) > 0:
                msg += "ROIs classified as Cris or ER:\n"
                for line in lines:
                    assigned = line.get("assigned_mito")
                    assigned_name = ""

                    if assigned is not None:
                        assigned_name = assigned["name"]

                    msg += "  - " + ascii_text(line["name"])
                    msg += "   type=" + ascii_text(line.get("roi_type", ""))
                    msg += "   mito=" + ascii_text(assigned_name)
                    msg += "   relationship=" + ascii_text(line.get("relationship", ""))
                    msg += "\n"

                msg += "\n"

            if len(other) > 0:
                msg += "Ignored ROIs:\n"
                for item in other:
                    msg += "  - " + ascii_text(item["name"]) + "\n"
                msg += "\n"

            if len(warnings) > 0:
                msg += "Warnings:\n"
                for w in warnings:
                    msg += "  - " + ascii_text(w) + "\n"

            IJ.showMessage("ROI Manager Check", ascii_text(msg))

            IJ.log("ROI Manager Check + Rename:")
            IJ.log("  Mito/area ROIs: " + str(len(mitos)))
            IJ.log("  ROI lines: " + str(len(lines)))
            IJ.log("  Other ignored ROIs: " + str(len(other)))

            self.refresh_overlay()

        except Exception as e:
            IJ.log("Mito/Cristae/ER tool ERROR during ROI check:")
            IJ.log(ascii_text(e))
            IJ.showMessage("Mito/Cristae/ER tool ERROR", ascii_text(e))

    def analyze(self, event):
        IJ.log("Mito/Cristae/ER tool: Analyze button clicked.")

        try:
            self.refresh_overlay()

            show_maps = self.cb_maps.isSelected()
            save_csv = self.cb_save_csv.isSelected()
            save_txt = self.cb_save_txt.isSelected()
            save_dir = self.ensure_save_folder_if_needed()

            if save_dir is None:
                save_csv = False
                save_txt = False

            run_analysis(show_maps, save_csv, save_txt, save_dir)

            self.refresh_overlay()
            IJ.log("Mito/Cristae/ER tool: Analyze finished.")

        except Exception as e:
            IJ.log("Mito/Cristae/ER tool ERROR during analysis:")
            IJ.log(ascii_text(e))
            IJ.showMessage("Mito/Cristae/ER tool ERROR", ascii_text(e))

    def toggle_mitos(self, event):
        self.show_mitos = not self.show_mitos

        if self.show_mitos:
            self.btn_toggle_mitos.setText("Hide Mitos")
        else:
            self.btn_toggle_mitos.setText("Show Mitos")

        self.refresh_overlay()

    def toggle_lines(self, event):
        self.show_lines = not self.show_lines

        if self.show_lines:
            self.btn_toggle_lines.setText("Hide Lines")
        else:
            self.btn_toggle_lines.setText("Show Lines")

        self.refresh_overlay()

    def show_all(self, event):
        self.show_mitos = True
        self.show_lines = True

        self.btn_toggle_mitos.setText("Hide Mitos")
        self.btn_toggle_lines.setText("Hide Lines")

        self.refresh_overlay()

    def hide_all(self, event):
        self.show_mitos = False
        self.show_lines = False

        self.btn_toggle_mitos.setText("Show Mitos")
        self.btn_toggle_lines.setText("Show Lines")

        self.refresh_overlay()

    def clear_rois(self, event):
        imp = get_current_image()
        rm = get_rm()

        if imp:
            imp.setOverlay(None)
            imp.updateAndDraw()

        try:
            rm.runCommand("Show None")
        except:
            pass

        try:
            rm.runCommand("Reset")
        except:
            pass

        self.show_mitos = False
        self.show_lines = False

        self.btn_toggle_mitos.setText("Show Mitos")
        self.btn_toggle_lines.setText("Show Lines")

        IJ.log("Mito/Cristae/ER tool: ROI Manager cleared.")


# ============================================================
# Launch tool
# ============================================================

MitoCristaeDistanceTool()