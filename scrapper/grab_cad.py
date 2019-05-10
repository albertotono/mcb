import logging
import os
import shutil
from datetime import datetime
from os.path import join

import db
import requests
import trimesh
import wget
from scrapper.base import filter_escape_char, unzip_file
from config import grabcad_path
from tqdm import tqdm
from trimesh.exchange.export import export_mesh
from utils import make_dir

grapcad_url = 'https://grabcad.com'
api_url = f'{grapcad_url}/community/api/v1/models'
login_url = f'{grapcad_url}/login'
sw_ext_mapping = {
    'stl': '.stl',
    'obj': '.obj',
    'ptc-creo-parametric': '.prt',
    'solidworks': '.sldprt',
}


def search(keyword, softwares, page=1, per_page=100, sort='following', time='all_time'):
    payload = {
        'page': str(page),
        'per_page': str(per_page),
        'query': keyword,
        'softwares': softwares,
        'sort': sort,
        'time': time,
    }
    r = requests.post(api_url, data=payload)
    if r.status_code == 200:
        models = []
        images = []
        for item in r.json()['models']:
            models.append(item['cached_slug'])
            images.append(item['preview_image'])
        return models, images, r.json()['total_entries']
    else:
        raise ConnectionError


def get_models(keyword, softwares=None):
    if softwares is None:
        softwares = ["obj"]
    per_page = 100
    model_names, images, total_models = search(keyword, per_page=per_page, softwares=softwares)
    insert_search_log(keyword, total_models, softwares)
    for i in tqdm(range(total_models // per_page)):
        model_name, image, _ = search(keyword, page=i + 2, softwares=softwares)
        model_names += model_name
        images += image
    print(f'{total_models} models found.')
    return model_names, images


def get_cadid(cached_slug):
    url = f'{api_url}/{cached_slug}'
    r = requests.get(url)
    if r.status_code == 200:
        if 'archive_url' in r.json():
            return r.json()['archive_url'].split('=')[-1]
        else:
            return None
    else:
        raise ConnectionError


def download_zipfile(cadid, output_dir):
    url = f'https://d2t1xqejof9utc.cloudfront.net/cads/files/{cadid}/original.zip'
    return wget.download(url, out=output_dir)


def filter_files(keyword, unzipped_dir, softwares):
    formats = [sw_ext_mapping[software] for software in softwares]
    files = []
    for file in os.listdir(unzipped_dir):
        filename, ext = os.path.splitext(file)
        if (ext.lower() in formats) and (keyword in filename.lower()):
            files.append(file)

    return files


def convert_to_obj(file):
    basename = os.path.basename(file)
    filename, ext = os.path.splitext(basename)
    if ext.lower() == '.stl':
        mesh = trimesh.load_mesh(file)
        obj_file = file.replace(ext, '.obj')
        export_mesh(mesh, obj_file, file_type='obj')
        os.remove(file)
        return obj_file
    else:
        return file


def insert_search_log(keyword, total, softwares):
    return db.insert('search_log',
                     **{
                         'keyword': keyword,
                         'etc': f"softwares : {';'.join(softwares)}",
                         'website': 'grabCAD',
                         'total': total
                     })


def insert_grabcad_model(model_name, cadid, image):
    return db.insert('grabcad_models', ignore=True, **{'name': model_name, 'id': cadid, 'image': image})


def insert_grabcad_file(cadid, filepath):
    return db.insert('grabcad_files', ignore=True, **{'cadid': cadid, 'file': filter_escape_char(filepath)})


def is_model(cadid):
    return not db.query(f"SELECT * from grabcad_files WHERE cadid='{cadid}'").empty


def run(keyword, softwares=None):
    keyword = keyword.lower()
    if softwares is None:
        softwares = ['obj']

    output_dir = f'{grabcad_path}/{keyword}'
    make_dir(output_dir)

    # search models
    model_names, model_images = get_models(keyword, softwares=softwares)

    for model_name, model_image in tqdm(zip(model_names, model_images)):
        model_name = filter_escape_char(model_name)

        # filter by model name
        if keyword not in model_name.lower():
            continue

        # check model validity
        cadid = get_cadid(model_name)
        if not cadid:
            continue

        # check db
        if is_model(cadid):
            continue

        insert_grabcad_model(model_name, cadid, model_image)

        # unzip model
        zip_file = download_zipfile(cadid, output_dir)
        unzipped_dir = unzip_file(zip_file)

        # extract files with valid extension
        files = filter_files(keyword, unzipped_dir, softwares)
        if not files:
            shutil.rmtree(unzipped_dir)
            continue

        # move valid files
        for file in files:
            moved_file = move_file(join(unzipped_dir, file), output_dir)
            obj_file = convert_to_obj(moved_file)
            insert_grabcad_file(cadid, obj_file)

        # remove unzipped directory
        shutil.rmtree(unzipped_dir)
