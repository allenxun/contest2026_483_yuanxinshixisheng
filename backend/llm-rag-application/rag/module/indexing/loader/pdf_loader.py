import os
import copy
from typing import List, Iterator
import cv2
from PIL import Image
from langchain_core.documents import Document
from langchain_community.document_loaders import UnstructuredFileLoader
from rag.module.indexing.loader.ocr import get_rapid_ocr
import tqdm
import numpy as np
import pymupdf
import re
from wired_table_rec import WiredTableRecognition

# PDF OCR 控制：只对宽高超过页面一定比例（图片宽/页面宽，图片高/页面高）的图片进行 OCR。
# 这样可以避免 PDF 中一些小图片的干扰，提高非扫描版 PDF 处理速度
PDF_OCR_THRESHOLD = (0.6, 0.6)


class CustomizedOcrPdfLoader(UnstructuredFileLoader):

    table_enhance: List = None

    def _is_paragraph_end(self, text):
        if text.strip()[-1] in ["。", "？"]:
            return True
        else:
            return False

    def _get_elements(self) -> List:
        def rotate_img(img, angle):
            '''
            img   --image
            angle --rotation angle
            return--rotated img
            '''

            h, w = img.shape[:2]
            rotate_center = (w / 2, h / 2)
            # 获取旋转矩阵
            # 参数1为旋转中心点;
            # 参数2为旋转角度,正值-逆时针旋转;负值-顺时针旋转
            # 参数3为各向同性的比例因子,1.0原图，2.0变成原来的2倍，0.5变成原来的0.5倍
            M = cv2.getRotationMatrix2D(rotate_center, angle, 1.0)
            # 计算图像新边界
            new_w = int(h * np.abs(M[0, 1]) + w * np.abs(M[0, 0]))
            new_h = int(h * np.abs(M[0, 0]) + w * np.abs(M[0, 1]))
            # 调整旋转矩阵以考虑平移
            M[0, 2] += (new_w - w) / 2
            M[1, 2] += (new_h - h) / 2

            rotated_img = cv2.warpAffine(img, M, (new_w, new_h))
            return rotated_img

        def clip_text_and_table(page):
            resp = ""
            resp_list = []
            # step 1: 提取表格（text-base）
            tabs = page.find_tables()

            # step 2: 识别文本
            # text_list = []
            # tab_text_list = []
            last_tab_bbox_y1 = page.rect.y0
            for tab in tabs:
                tab_bbox = pymupdf.Rect(tab.bbox)

                top_bbox = page.rect
                top_bbox.y0 = last_tab_bbox_y1
                top_bbox.y1 = tab_bbox.y0
                text = page.get_text("", clip=top_bbox)
                if text:
                    for sub_text in text.split("\n"):
                        if not sub_text.strip() or sub_text.strip().isdigit(): continue
                        if self._is_paragraph_end(sub_text):
                            resp_list.append(resp + sub_text)
                            resp = ""
                        else:
                            resp += sub_text.strip()
                header = tab.header
                external = header.external
                names = header.names
                tab_md_text = tab.to_pandas().to_markdown().replace(" ", "").replace("\n", "")
                if resp:
                    resp_list.append(resp + tab_md_text)
                    resp = ""
                else:
                    resp_list.append(tab_md_text)

                last_tab_bbox_y1 = tab_bbox.y1

            # 被最后一个tab切分剩下的文档块
            btm_bbox = page.rect
            btm_bbox.y0 = last_tab_bbox_y1
            text = page.get_text("", clip=btm_bbox)
            # resp += text + "\n"
            if text:
                for sub_text in text.split("\n"):
                    if not sub_text.strip() or sub_text.strip().isdigit(): continue
                    if self._is_paragraph_end(sub_text):
                        resp_list.append(resp + sub_text)
                        resp = ""
                    else:
                        resp += sub_text.strip()

            return resp_list

        def pdf2text(filepath):

            table_rec = WiredTableRecognition()
            rapid_ocr = get_rapid_ocr()
            doc = pymupdf.open(filepath)
            resp = ""
            resp_list = []
            tab_resp_list = []

            b_unit = tqdm.tqdm(total=doc.page_count, desc="CustomizedOcrPdfLoader context page index: 0")
            for i, page in enumerate(doc):
                b_unit.set_description("CustomizedOcrPdfLoader context page index: {}".format(i))
                b_unit.refresh()

                text = page.get_text("")
                # resp += text + "\n"
                if text:
                    for sub_text in text.split("\n"):
                        if not sub_text.strip() or sub_text.strip().isdigit(): continue
                        if self._is_paragraph_end(sub_text):
                            resp_list.append(resp + sub_text)
                            resp = ""
                        else:
                            resp += sub_text.strip()
                    # if resp: resp_list.append(resp)

                # OCR
                img_list = page.get_image_info(xrefs=True)
                for img in img_list:
                    if xref := img.get("xref"):
                        bbox = img["bbox"]
                        # 检查图片尺寸是否超过设定的阈值
                        if ((bbox[2] - bbox[0]) / (page.rect.width) < PDF_OCR_THRESHOLD[0]
                                or (bbox[3] - bbox[1]) / (page.rect.height) < PDF_OCR_THRESHOLD[1]):
                            continue
                        pix = pymupdf.Pixmap(doc, xref)
                        samples = pix.samples
                        if int(page.rotation) != 0:  # 如果Page有旋转角度，则旋转图片
                            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, -1)
                            tmp_img = Image.fromarray(img_array);
                            ori_img = cv2.cvtColor(np.array(tmp_img), cv2.COLOR_RGB2BGR)
                            rot_img = rotate_img(img=ori_img, angle=360 - page.rotation)
                            img_array = cv2.cvtColor(rot_img, cv2.COLOR_RGB2BGR)
                        else:
                            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, -1)

                        # result, _ = rapid_ocr(img_array)
                        # if result:
                        #     ocr_result = [line[1] for line in result]
                        #     resp += "\n".join(ocr_result)

                        # rapid ocr识别文本内容
                        rapid_ocr_result, _ = rapid_ocr(img_array)
                        if not rapid_ocr_result: continue
                        rapid_ocr_result = [line[1] for line in rapid_ocr_result]
                        for text in rapid_ocr_result:
                            if text.strip().isdigit(): continue
                            if self._is_paragraph_end(text):
                                resp_list.append(resp + text)
                                resp = ""
                            else:
                                resp += text.strip()
                        # if resp: resp_list.append(resp)

                        # TableStructureRec 识别图像中表格
                        table_str, elapse = table_rec(img_array)
                        if table_str:
                            table_ele_index = []
                            for index, t in enumerate(rapid_ocr_result):
                                if t in table_str: table_ele_index.append(index)
                            index = min(table_ele_index) if table_ele_index else 0
                            table_name = rapid_ocr_result[:index][-1] if rapid_ocr_result[:index] else ""
                            # print(i, table_name, table_str)
                            tab_resp_list.append([table_name, table_str])

                # table (text-based)
                tabs = page.find_tables()
                for tab in tabs:
                    header = tab.header
                    external = header.external
                    names = header.names
                    table_name = ""
                    if external:    # 将表名误识别成了feature
                        table_name = "".join(header.names)
                    else:
                        tab_bbox = pymupdf.Rect(tab.bbox)
                        top_bbox = page.rect
                        top_bbox.y1 = tab_bbox.y0
                        top_text = page.get_text("", clip=top_bbox)
                        for t in top_text.split("\n")[::-1]:
                            if not t.strip(): continue
                            table_name = t
                            break
                        if not table_name and tab_resp_list:
                            table_name = tab_resp_list[-1][0]
                    tab_text = tab.to_pandas().to_markdown(index=False)
                    tab_text = re.sub(r'-{2,}', '---', tab_text)
                    tab_text = re.sub(r' {2,}', ' ', tab_text)
                    # print("===============================\n")
                    # print(i, external, "\n")
                    # print("表头：", table_name, "\n")
                    # print(names, "\n")
                    # print(tab_text, "\n")
                    # tab_resp_list.append(table_name + "\n" + tab_text)
                    tab_resp_list.append([table_name, tab_text])

                # 更新进度
                b_unit.update(1)
            # return resp
            if tab_resp_list: self.table_enhance = [table_info[0] + "\n" + table_info[1] for table_info in tab_resp_list]
            if resp: resp_list.append(resp)
            return "\n".join(resp_list)

        text = pdf2text(self.file_path)
        from unstructured.partition.text import partition_text
        return partition_text(text=text, **self.unstructured_kwargs)

    def lazy_load(self) -> Iterator[Document]:
        """Load file."""
        elements = self._get_elements()
        if self.mode == "single":
            metadata = self._get_metadata()
            text = "\n\n".join([str(el) for el in elements])
            if not self.table_enhance:
                yield Document(page_content=text, metadata=metadata)
            else:
                for doc in ([Document(page_content=text, metadata=metadata)] + \
                            [Document(page_content=table, metadata=copy.deepcopy(metadata)) for table in self.table_enhance]):
                    yield doc
        else:
            raise ValueError(f"mode of {self.mode} not supported.")


if __name__ == "__main__":
    import nltk, os
    nltk.data.path = [os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "nltk_data")] \
                     + nltk.data.path

    # file_path = "/Users/ethan/Documents/projects/tecorigin/行业项目/水利/发太初资料/河长制资料/政策资料/10.重庆市总河长令（第1号）.pdf"
    # file_path = "/Users/ethan/Documents/projects/tecorigin/行业项目/水利/发太初资料/河长制资料/政策资料/河湖健康评价指南（试行）.pdf"
    # file_path = "/Users/ethan/Documents/projects/tecorigin/行业项目/水利/发太初资料/河长制资料/政策资料/重庆幸福河湖评价指标体系.pdf"
    # file_path = "/Users/ethan/Documents/projects/tecorigin/行业项目/水利/发太初资料/河长制资料/一河一策/阿蓬江.pdf"
    file_path = "/Users/ethan/Documents/projects/tecorigin/行业项目/水利/发太初资料/河长制资料/政策资料/2..重庆市全面推行河长制工作方案.pdf"

    loader = CustomizedOcrPdfLoader(
        file_path=file_path)
    docs = loader.load()

    for doc in docs:
        print("\n\n======================================")
        print(doc.page_content)

