#!/usr/bin/env python

import argparse
import collections
import datetime
import glob
import json
import os
import os.path as osp
import sys
import uuid

import imgviz
import numpy as np

import labelme
from itertools import islice

import pycocotools.mask


def main(args):
    if args.crop:
        args.input_dir = args.input_dir + '_crop'
        args.output_dir = args.output_dir + '_crop'
    modes = os.listdir(args.input_dir)

    if osp.exists(args.output_dir):
            print("Output directory already exists:", args.output_dir)
            sys.exit(1)
    os.makedirs(args.output_dir)
            
    for mode in modes:
        input_dir = os.path.join(args.input_dir, mode)
        output_dir = os.path.join(args.output_dir, mode)
        os.makedirs(osp.join(output_dir, "JPEGImages"))
        if not args.noviz:
            os.makedirs(osp.join(output_dir, "Visualization"))
        print("Creating dataset:", output_dir)

        now = datetime.datetime.now()

        data = dict(
            info=dict(
                description=None,
                url=None,
                version=None,
                year=now.year,
                contributor=None,
                date_created=now.strftime("%Y-%m-%d %H:%M:%S.%f"),
            ),
            licenses=[dict(url=None, id=0, name=None,)],
            images=[
                # license, url, file_name, height, width, date_captured, id
            ],
            type="instances",
            annotations=[
                # segmentation, area, iscrowd, image_id, bbox, category_id, id
            ],
            categories=[
                # supercategory, id, name
            ],
        )

        class_name_to_id = {}
        for i, line in enumerate(open(args.labels).readlines()):
            class_id = i - 1  # starts with -1
            class_name = line.strip()
            if class_id == -1:
                assert class_name == "__ignore__"
                continue
            class_name_to_id[class_name] = class_id
            data["categories"].append(
                dict(supercategory=None, id=class_id, name=class_name,)
            )

        out_ann_file = osp.join(output_dir, "{}.json".format(mode))
        label_files = glob.glob(osp.join(input_dir, "*.json"))

        for image_id, filename in enumerate(label_files):
            print("Generating dataset from:", filename)

            label_file = labelme.LabelFile(filename=filename)

            base = osp.splitext(osp.basename(filename))[0]
            out_img_file = osp.join(output_dir, "JPEGImages", base + ".jpg")

            img = labelme.utils.img_data_to_arr(label_file.imageData)
            imgviz.io.imsave(out_img_file, img)
            data["images"].append(
                dict(
                    license=0,
                    url=None,
                    file_name=osp.relpath(out_img_file, osp.dirname(out_ann_file)),
                    height=img.shape[0],
                    width=img.shape[1],
                    date_captured=None,
                    id=image_id,
                )
            )

            masks = {}  # for area
            segmentations = collections.defaultdict(list)  # for segmentation
            for shape in label_file.shapes:
                points = shape["points"]
                label = shape["label"]
                group_id = shape.get("group_id")
                shape_type = 'polygon'#shape.get("shape_type", "polygon")
                #print(shape_type)

                try:
                    mask = labelme.utils.shape_to_mask(
                        img.shape[:2], points, shape_type
                    )
                except Exception as e:
                    print(e, filename)
                    continue
                if group_id is None:
                    group_id = uuid.uuid1()

                instance = (label, group_id)

                if instance in masks:
                    masks[instance] = masks[instance] | mask
                else:
                    masks[instance] = mask

                if shape_type == "rectangle":
                    (x1, y1), (x2, y2) = points
                    x1, x2 = sorted([x1, x2])
                    y1, y2 = sorted([y1, y2])
                    points = [x1, y1, x2, y1, x2, y2, x1, y2]
                else:
                    points = np.asarray(points).flatten().tolist()

                segmentations[instance].append(points)
            segmentations = dict(segmentations)

            for instance, mask in masks.items():
                cls_name, group_id = instance
                if cls_name not in class_name_to_id:
                    continue
                cls_id = class_name_to_id[cls_name]

                mask = np.asfortranarray(mask.astype(np.uint8))
                mask = pycocotools.mask.encode(mask)
                area = float(pycocotools.mask.area(mask))
                bbox = pycocotools.mask.toBbox(mask).flatten().tolist()

                data["annotations"].append(
                    dict(
                        id=len(data["annotations"]),
                        image_id=image_id,
                        category_id=cls_id,
                        segmentation=segmentations[instance],
                        area=area,
                        bbox=bbox,
                        iscrowd=0,
                    )
                )

            if not args.noviz:
                # for (cnm, gid), msk in masks.items():
                #     print(cnm, gid, mask)
                #     print(cnm in class_name_to_id)
                #     print(class_name_to_id)
                labels, captions, masks = zip(
                    *[
                        (class_name_to_id[cnm], cnm, msk)
                        for (cnm, gid), msk in masks.items()
                        if cnm in class_name_to_id
                    ]
                )
                viz = imgviz.instances2rgb(
                    image=img,#imgviz.gray2rgb(img),
                    labels=labels,
                    masks=masks,
                    captions=captions,
                    font_size=15,
                    line_width=2,
                )
                out_viz_file = osp.join(
                    output_dir, "Visualization", base + ".jpg"
                )
                imgviz.io.imsave(out_viz_file, viz)

        with open(out_ann_file, "w") as f:
            json.dump(data, f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--input_dir", default='../datasets', help="input annotated directory")
    parser.add_argument("--output_dir", default='../coco_datasets', help="output dataset directory")
    parser.add_argument("--labels", help="labels file", default='./labels.txt')
    parser.add_argument(
        "--noviz", help="no visualization", action="store_true"
    )
    parser.add_argument('--crop', action='store_true')
    args = parser.parse_args()
    
    main(args)
