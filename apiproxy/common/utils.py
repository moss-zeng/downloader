#!/usr/bin/env python
# -*- coding: utf-8 -*-


import random
import requests
import re
import os
import sys
import hashlib
import base64
import time

import apiproxy


class Utils (object):
    def __init__(self):
        pass

    def replaceStr (self, filenamestr: str):
        """
        替换非法字符，缩短字符长度，使其能成为文件名
        """
        # 匹配 汉字 字母 数字 空格
        match = "([0-9A-Za-z\u4e00-\u9fa5]+)"

        result = re.findall(match, filenamestr)

        result = "".join(result).strip()
        if len (result) > 20:
            result = result [:20]
        # 去除前后空格
        return result

    def resource_path (self, relative_path):
        if getattr (sys, 'frozen', False):  # 是否 Bundle Resource
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, relative_path)

    def str2bool (self, v):
        if isinstance (v, bool):
            return v
        if v.lower() in ('yes', 'true', 't', 'y', '1'):
            return True
        elif v.lower() in ('no', 'false', 'f', 'n', '0'):
            return False
        else:
            return True

    def generate_random_str (self, randomlength = 16):
        """
        根据传入长度产生随机字符串
        """
        random_str = ''
        base_str = 'ABCDEFGHIGKLMNOPQRSTUVWXYZabcdefghigklmnopqrstuvwxyz0123456789='
        length = len (base_str) - 1
        for _ in range (randomlength):
            random_str += base_str [random.randint(0, length)]
        return random_str

    # https://www.52pojie.cn/thread-1589242-1-1.html
    def getttwid (self):
        url = 'https://ttwid.bytedance.com/ttwid/union/register/'
        data = '{"region":"cn","aid":1768,"needFid":false,"service":"www.ixigua.com","migrate_info":{"ticket":"","source":"node"},"cbUrlProtocol":"https","union":true}'
        res = requests.post(url = url, data = data)

        for i, j in res.cookies.items():
            return j



if __name__ == "__main__":
    pass