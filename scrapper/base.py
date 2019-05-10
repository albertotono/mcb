import os


def filter_escape_char(char):
    return char.replace("\'", "\'\'")


def remove_escape_char(char):
    return char.replace("\'", "\'\'")


def unzip_file(zip_file, output_dir=None):
    if not output_dir:
        output_dir = zip_file.replace('.zip', '')

    # import zipfile
    # zip_ref = zipfile.ZipFile(zip_file, 'r')
    # zip_ref.extractall()
    # zip_ref.close()
    os.system(f'unzip -o {zip_file} -d {output_dir}')
    os.remove(zip_file)
    return output_dir


def move_file(file, dst_dir):
    basename = os.path.basename(file)
    head, tail = os.path.splitext(basename)
    dst_file = os.path.join(dst_dir, basename)

    count = 0
    while os.path.exists(dst_file):
        count += 1
        dst_file = os.path.join(dst_dir, '%s-%d%s' % (head, count, tail))

    shutil.move(file, dst_file)
    return dst_file
