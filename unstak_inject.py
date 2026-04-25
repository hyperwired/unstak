import os

TARGET_START_MARKER = "# UNSTAK_START"
TARGET_END_MARKER = "# UNSTAK_END"

TARGET_FILE = "balance.py"
SOURCE_FILE = "unstak_balancer.py"


def inject_code(source_file, target_file, target_start_marker, target_end_marker):
    assert os.path.isfile(source_file) and os.path.isfile(target_file)
    target_lines = []
    source_lines = []
    with open(target_file) as fh:
        target_lines = fh.readlines()
    with open(source_file) as fh:
        source_lines = fh.readlines()

    start_marker_line = None
    end_marker_line = None
    for i, target_line in enumerate(target_lines):
        if target_line.startswith(target_start_marker):
            assert start_marker_line is None
            start_marker_line = i
        elif target_line.startswith(target_end_marker):
            assert end_marker_line is None
            end_marker_line = i
    assert start_marker_line is not None and end_marker_line is not None and end_marker_line > start_marker_line

    print("injecting %d source lines from %s into lines %d-%d of %s" %
          (len(source_lines), source_file, start_marker_line, end_marker_line, target_file))

    target_output_lines = target_lines[:start_marker_line]
    target_output_lines.extend(source_lines)
    target_output_lines.extend(target_lines[end_marker_line+1:])

    with open(target_file, "w") as fh:
        fh.writelines(target_output_lines)


def main():
    inject_code(SOURCE_FILE, TARGET_FILE, TARGET_START_MARKER, TARGET_END_MARKER)


if __name__ == "__main__":
    main()

