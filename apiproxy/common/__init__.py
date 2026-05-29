#!/usr/bin/env python
# -*- coding: utf-8 -*-

from .utils import Utils
from .douyin_utils import DouyinUtils
from . import tiktok_utils         

utils = Utils()                     # 通用：replaceStr 等，web_app.py 在用
douyin_utils = DouyinUtils()        # 抖音签名实例