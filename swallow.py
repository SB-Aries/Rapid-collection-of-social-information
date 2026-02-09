import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
import requests
import os
import json
from urllib.parse import urlparse

# 配置正则表达式
# 邮箱正则
EMAIL_PATTERN = r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}'
# 中国手机号正则（覆盖+86、空格、-、纯11位等常见格式）
CHINA_PHONE_PATTERN = r'(?:\+86\s?)?1[3-9]\d{9}|(?:\+86\s?)?1[3-9]\d{1}\s?\d{4}\s?\d{4}|(?:\+86\s?)?1[3-9]\d{2}-\d{4}-\d{4}'
# 学号正则表达式 - 支持多种常见格式
# 根据最新学号格式标准更新（2026-02-09）
# 年份限制：只匹配2000年以后的学号

# 基础格式 - 根据新格式重新定义
# 1. 数字型（包括10位、12位、9位、6-8位等）
STUDENT_ID_NUMERIC = r'\b(20\d{2}\d{6}|20\d{2}\d{8}|\d{3}\d{6}|20\d{2}\d{5}|\d{6,8})\b'
# 2. 字母数字混合型（包含字母前缀、中缀或后缀）
STUDENT_ID_ALPHANUMERIC = r'\b([BMDY]20\d{2}\d{4,6}|20\d{2}[A-Z]\d{4,5}|20\d{2}\d{4,6}[A-Z]|[A-Z0-9]{8,12})\b'
# 3. 包含分隔符的格式（根据新格式，暂时不支持带分隔符的学号）
STUDENT_ID_WITH_SEPARATOR = r''

# 预定义学号模板 - 根据新格式更新
# 1. 10位纯数字（4位入学年份+2位学院码+2位专业码+2位个人序号）
STUDENT_ID_TEMPLATE_10DIGIT = r'\b20\d{2}\d{6}\b'
# 2. 12位纯数字（4位入学年份+2位校区码+2位学院码+2位专业码+2位个人序号）
STUDENT_ID_TEMPLATE_12DIGIT = r'\b20\d{2}\d{8}\b'
# 3. 9位纯数字（部分老牌本科、专科院校）
STUDENT_ID_TEMPLATE_9DIGIT = r'\b\d{3}\d{6}\b|\b20\d{2}\d{5}\b'
# 4. 含字母的学号（中外合作办学、研究生、特色院校）
STUDENT_ID_TEMPLATE_WITH_LETTER = r'\b[BMDY]20\d{2}\d{4,6}\b|\b20\d{2}[A-Z]\d{4,5}\b|\b20\d{2}\d{4,6}[A-Z]\b|\b[A-Z0-9]{8,12}\b'
# 5. 6-8位纯数字（中小学、高职院校）
STUDENT_ID_TEMPLATE_SHORT = r'\b\d{6,8}\b'

# 综合学号正则（匹配上述所有常见格式）
# ALL模式：包含所有内置学号格式
STUDENT_ID_PATTERN = (STUDENT_ID_TEMPLATE_10DIGIT + '|' + 
                     STUDENT_ID_TEMPLATE_12DIGIT + '|' + 
                     STUDENT_ID_TEMPLATE_9DIGIT + '|' + 
                     STUDENT_ID_TEMPLATE_WITH_LETTER + '|' + 
                     STUDENT_ID_TEMPLATE_SHORT)

# 模板文件路径
TEMPLATE_FILE = os.path.join(os.path.expanduser("~"), ".student_id_templates.json")

class WebScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("社工信息快速收集工具2.0- GUI")
        self.root.geometry("900x700")
        
        # 改用集合存储结果（天然去重，效率更高）
        self.all_email_results = set()  # 所有URL的唯一邮箱
        self.all_phone_results = set()  # 所有URL的唯一手机号
        self.all_student_id_results = set()  # 所有URL的唯一学号
        self.current_urls = []          # 当前待爬取的URL列表（批量模式）
        
        # 学号格式配置
        self.student_id_pattern = STUDENT_ID_PATTERN  # 当前使用的学号正则
        self.custom_student_id_pattern = tk.StringVar()  # 自定义学号格式
        # 预定义模板字典
        self.student_id_templates = {
            "ALL模式": STUDENT_ID_PATTERN,
            "10位纯数字（综合类本科）": STUDENT_ID_TEMPLATE_10DIGIT,
            "12位纯数字（规模较大院校）": STUDENT_ID_TEMPLATE_12DIGIT,
            "9位纯数字（老牌院校）": STUDENT_ID_TEMPLATE_9DIGIT,
            "含字母学号（特色院校）": STUDENT_ID_TEMPLATE_WITH_LETTER,
            "6-8位纯数字（中小学/高职）": STUDENT_ID_TEMPLATE_SHORT
        }  # 学号格式模板存储
        
        # 从文件加载用户自定义模板
        self._load_templates_from_file()
        
        # 创建界面组件
        self._create_widgets()
    
    def _create_widgets(self):
        # 1. 模式选择区域
        mode_frame = ttk.LabelFrame(self.root, text="爬取模式")
        mode_frame.pack(fill="x", padx=10, pady=5)
        
        self.mode_var = tk.StringVar(value="single")  # single:单URL, batch:批量
        single_radio = ttk.Radiobutton(mode_frame, text="单URL爬取", variable=self.mode_var, 
                                      value="single", command=self._switch_mode)
        single_radio.pack(side="left", padx=20, pady=5)
        
        batch_radio = ttk.Radiobutton(mode_frame, text="批量URL爬取", variable=self.mode_var, 
                                      value="batch", command=self._switch_mode)
        batch_radio.pack(side="left", padx=20, pady=5)
        
        # 2. URL/文件输入区域
        input_frame = ttk.LabelFrame(self.root, text="URL")
        input_frame.pack(fill="x", padx=10, pady=5)
        
        # 单URL输入框
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(input_frame, textvariable=self.url_var, font=("Arial", 14))
        self.url_entry.pack(fill="x", padx=10, pady=5, ipady=3)
        
        # 批量文件选择按钮（默认隐藏）
        self.file_btn = ttk.Button(input_frame, text="选择TXT文件（每行一个URL）", command=self._select_batch_file)
        self.file_label = ttk.Label(input_frame, text="未选择文件", font=("Arial", 14), foreground="gray")
        
        # 3. 爬取选项区域
        option_frame = ttk.LabelFrame(self.root, text="爬取选项")
        option_frame.pack(fill="x", padx=10, pady=5)
        
        # 邮箱复选框
        self.email_var = tk.BooleanVar(value=True)
        email_check = ttk.Checkbutton(option_frame, text="爬取邮箱", variable=self.email_var)
        email_check.pack(side="left", padx=20, pady=5)
        
        # 手机号复选框
        self.phone_var = tk.BooleanVar(value=True)
        phone_check = ttk.Checkbutton(option_frame, text="爬取手机号", variable=self.phone_var)
        phone_check.pack(side="left", padx=20, pady=5)
        
        # 学号复选框
        self.student_id_var = tk.BooleanVar(value=False)
        student_id_check = ttk.Checkbutton(option_frame, text="爬取学号", variable=self.student_id_var)
        student_id_check.pack(side="left", padx=20, pady=5)
        
        # 4. 学号格式配置区域
        student_id_frame = ttk.LabelFrame(self.root, text="学号格式配置")
        student_id_frame.pack(fill="x", padx=10, pady=5)
        
        # 学号格式模板选择
        ttk.Label(student_id_frame, text="选择格式模板:").pack(anchor="w", padx=10, pady=2)
        self.template_var = tk.StringVar(value="ALL模式")
        # 获取所有模板名称
        template_names = list(self.student_id_templates.keys())
        self.template_combo = ttk.Combobox(student_id_frame, textvariable=self.template_var, values=template_names)
        self.template_combo.pack(fill="x", padx=10, pady=2)
        self.template_combo.bind("<<ComboboxSelected>>", self._load_template)
        
        # 自定义学号格式输入
        ttk.Label(student_id_frame, text="自定义正则表达式:").pack(anchor="w", padx=10, pady=2)
        self.custom_pattern_entry = ttk.Entry(student_id_frame, textvariable=self.custom_student_id_pattern, font=(
"Arial", 12))
        self.custom_pattern_entry.pack(fill="x", padx=10, pady=2)
        # 正则表达式示例
        example_text = "示例: \\b\\d{10}\\b (10位数字)、\\b[A-Za-z]\\d{7}\\b (字母+7位数字)、\\b\\d{4}-\\d{6}\\b (带连字符)"
        ttk.Label(student_id_frame, text=example_text, foreground="gray", font=("Arial", 9)).pack(anchor="w", padx=10, pady=1)
        # 实时格式校验反馈标签
        self.pattern_feedback_var = tk.StringVar(value="")
        self.pattern_feedback_label = ttk.Label(student_id_frame, textvariable=self.pattern_feedback_var, foreground="red", font=("Arial", 10))
        self.pattern_feedback_label.pack(anchor="w", padx=10, pady=1)
        # 绑定实时校验事件
        self.custom_pattern_entry.bind("<KeyRelease>", self._validate_pattern_realtime)
        
        # 保存模板按钮
        save_template_btn = ttk.Button(student_id_frame, text="保存当前格式为模板", command=self._save_template)
        save_template_btn.pack(side="left", padx=10, pady=5)
        
        # 测试格式按钮
        test_pattern_btn = ttk.Button(student_id_frame, text="测试格式", command=self._test_student_id_pattern)
        test_pattern_btn.pack(side="left", padx=10, pady=5)
        
        # 清除模板按钮
        clear_template_btn = ttk.Button(student_id_frame, text="清除选中模板", command=self._clear_template)
        clear_template_btn.pack(side="left", padx=10, pady=5)
        
        # 5. 按钮区域
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)
        
        start_btn = ttk.Button(btn_frame, text="开始爬取", command=self.start_scraping)
        start_btn.pack(side="left", padx=10, pady=5)
        
        save_btn = ttk.Button(btn_frame, text="保存结果", command=self.save_results)
        save_btn.pack(side="left", padx=10, pady=5)
        
        clear_btn = ttk.Button(btn_frame, text="清空结果", command=self.clear_results)
        clear_btn.pack(side="left", padx=10, pady=5)
        
        # 新增：手动去重按钮（可选，用于主动去重）
        dedupe_btn = ttk.Button(btn_frame, text="手动去重结果", command=self.manual_dedupe)
        dedupe_btn.pack(side="left", padx=10, pady=5)
        
        # 5. 结果显示区域
        result_frame = ttk.LabelFrame(self.root, text="爬取结果（自动去重）")
        result_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(result_frame)
        scrollbar.pack(side="right", fill="y")
        
        # 结果文本框
        self.result_text = tk.Text(result_frame, yscrollcommand=scrollbar.set, font=("Arial", 14))
        self.result_text.pack(fill="both", expand=True, padx=5, pady=5)
        scrollbar.config(command=self.result_text.yview)
        
        # 设置文本框只读（默认）
        self.result_text.config(state=tk.DISABLED)
    
    def _switch_mode(self):
        """切换单URL/批量模式的界面显示"""
        mode = self.mode_var.get()
        if mode == "single":
            # 显示单URL输入框，隐藏批量文件相关组件
            self.url_entry.pack(fill="x", padx=10, pady=5, ipady=3)
            self.file_btn.pack_forget()
            self.file_label.pack_forget()
        else:
            # 隐藏单URL输入框，显示批量文件相关组件
            self.url_entry.pack_forget()
            self.file_btn.pack(fill="x", padx=10, pady=5, ipady=3)
            self.file_label.pack(fill="x", padx=10, pady=2)
    
    def _select_batch_file(self):
        """选择批量URL的TXT文件"""
        file_path = filedialog.askopenfilename(
            title="选择包含URL的TXT文件",
            filetypes=[("TXT文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            self.batch_file_path = file_path
            self.file_label.config(text=f"已选择：{os.path.basename(file_path)}", foreground="black")
            # 预读取URL并去重、过滤空行
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_urls = [line.strip() for line in f if line.strip()]
                    self.current_urls = list(set(raw_urls))  # URL本身先去重
                self._log(f"成功读取TXT文件，原始URL数：{len(raw_urls)}，去重后URL数：{len(self.current_urls)}", "blue")
            except Exception as e:
                messagebox.showerror("错误", f"读取文件失败：{str(e)}")
                self.file_label.config(text="文件读取失败", foreground="red")
    
    def _log(self, message, color="black"):
        """日志输出到结果文本框"""
        self.result_text.config(state=tk.NORMAL)
        self.result_text.insert(tk.END, f"{message}\n")
        self.result_text.tag_add(color, "end-{}c".format(len(message)+2), "end-1c")
        self.result_text.tag_config("red", foreground="red")
        self.result_text.tag_config("green", foreground="green")
        self.result_text.tag_config("blue", foreground="blue")
        self.result_text.see(tk.END)
        self.result_text.config(state=tk.DISABLED)
        self.root.update_idletasks()
    
    def _check_internet(self):
        """检查网络连接"""
        self._log("正在检查网络连接...", "blue")
        try:
            response = requests.get("http://www.baidu.com", timeout=5)
            if response.status_code == 200:
                self._log("网络连接正常", "green")
                return True
            else:
                self._log("网络连接异常", "red")
                return False
        except Exception as e:
            self._log(f"网络检查失败：{str(e)}", "red")
            return False
    
    def _validate_url(self, url):
        """验证URL格式"""
        if not url:
            return False
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
    
    def _validate_student_id(self, student_id, custom_pattern=None):
        """验证学号格式
        Args:
            student_id: 学号字符串
            custom_pattern: 自定义正则表达式模式（可选）
        Returns:
            bool: 是否符合格式
        """
        if not student_id:
            return False
        
        # 使用自定义模式或默认模式
        pattern = custom_pattern if custom_pattern else STUDENT_ID_PATTERN
        return bool(re.fullmatch(pattern, student_id))
    
    def _load_template(self, event):
        """加载选中的学号格式模板"""
        template_name = self.template_var.get()
        if template_name == "ALL模式":
            self.custom_student_id_pattern.set("")
            self.student_id_pattern = STUDENT_ID_PATTERN
        else:
            if template_name in self.student_id_templates:
                pattern = self.student_id_templates[template_name]
                self.custom_student_id_pattern.set(pattern)
                self.student_id_pattern = pattern
    
    def _save_template(self):
        """保存当前学号格式为模板"""
        pattern = self.custom_student_id_pattern.get().strip()
        if not pattern:
            messagebox.showwarning("提示", "请先输入自定义正则表达式")
            return
        
        # 简单验证正则表达式有效性
        try:
            re.compile(pattern)
        except re.error as e:
            messagebox.showerror("错误", f"无效的正则表达式：{str(e)}")
            return
        
        # 弹出对话框输入模板名称
        from tkinter.simpledialog import askstring
        template_name = askstring("保存模板", "请输入模板名称：")
        if template_name:
            template_name = template_name.strip()
            if not template_name:
                messagebox.showwarning("提示", "模板名称不能为空")
                return
            
            # 保存模板
            self.student_id_templates[template_name] = pattern
            
            # 更新下拉菜单
            templates = ["ALL模式"] + list(self.student_id_templates.keys())
            self.template_combo['values'] = templates
            
            # 保存模板到文件
            self._save_templates_to_file()
            
            messagebox.showinfo("成功", f"模板 '{template_name}' 已保存")
    
    def _test_student_id_pattern(self):
        """测试学号格式"""
        from tkinter.simpledialog import askstring
        test_id = askstring("测试格式", "请输入学号进行测试：")
        if test_id:
            test_id = test_id.strip()
            pattern = self.custom_student_id_pattern.get().strip() or STUDENT_ID_PATTERN
            
            try:
                if self._validate_student_id(test_id, pattern):
                    messagebox.showinfo("测试结果", f"学号 '{test_id}' 符合当前格式要求")
                else:
                    messagebox.showwarning("测试结果", f"学号 '{test_id}' 不符合当前格式要求")
            except re.error as e:
                messagebox.showerror("错误", f"正则表达式错误：{str(e)}")
    
    def _clear_template(self):
        """清除选中的学号格式模板"""
        template_name = self.template_var.get()
        if template_name == "ALL模式":
            messagebox.showinfo("提示", "ALL模式无法清除")
            return
        
        if template_name in self.student_id_templates:
            del self.student_id_templates[template_name]
            
            # 更新下拉菜单
            templates = ["ALL模式"] + list(self.student_id_templates.keys())
            self.template_combo['values'] = templates
            self.template_var.set("ALL模式")
            self.custom_student_id_pattern.set("")
            self.student_id_pattern = STUDENT_ID_PATTERN
            self.pattern_feedback_var.set("")  # 清空反馈
            
            # 保存模板到文件
            self._save_templates_to_file()
            
            messagebox.showinfo("成功", f"模板 '{template_name}' 已清除")
    
    def _load_templates_from_file(self):
        """从文件中加载保存的模板"""
        try:
            if os.path.exists(TEMPLATE_FILE):
                with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
                    saved_templates = json.load(f)
                    # 将保存的模板合并到当前模板字典中
                    self.student_id_templates.update(saved_templates)
        except Exception as e:
            self._log(f"加载模板文件失败：{str(e)}", "red")
    
    def _save_templates_to_file(self):
        """将当前模板保存到文件"""
        try:
            # 只保存用户自定义的模板，排除预定义模板
            predefined_templates = {
                "ALL模式": STUDENT_ID_PATTERN,
                "10位纯数字（综合类本科）": STUDENT_ID_TEMPLATE_10DIGIT,
                "12位纯数字（规模较大院校）": STUDENT_ID_TEMPLATE_12DIGIT,
                "9位纯数字（老牌院校）": STUDENT_ID_TEMPLATE_9DIGIT,
                "含字母学号（特色院校）": STUDENT_ID_TEMPLATE_WITH_LETTER,
                "6-8位纯数字（中小学/高职）": STUDENT_ID_TEMPLATE_SHORT
            }
            # 只保存用户自定义的模板
            user_templates = {}
            for name, pattern in self.student_id_templates.items():
                if name not in predefined_templates or predefined_templates[name] != pattern:
                    user_templates[name] = pattern
            
            with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
                json.dump(user_templates, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log(f"保存模板文件失败：{str(e)}", "red")
    
    def _validate_pattern_realtime(self, event):
        """实时验证用户输入的正则表达式"""
        pattern = self.custom_student_id_pattern.get().strip()
        if not pattern:
            self.pattern_feedback_var.set("")
            self.student_id_pattern = STUDENT_ID_PATTERN
            return
        
        try:
            # 尝试编译正则表达式
            re.compile(pattern)
            self.pattern_feedback_var.set("✓ 正则表达式格式有效")
            self.pattern_feedback_label.config(foreground="green")
            self.student_id_pattern = pattern
        except re.error as e:
            self.pattern_feedback_var.set(f"✗ 无效的正则表达式: {str(e)}")
            self.pattern_feedback_label.config(foreground="red")
    
    def _scrape_content(self, url):
        """爬取单个URL的网页内容"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = response.apparent_encoding  # 自动识别编码
            return response.text
        except Exception as e:
            self._log(f"爬取 {url} 失败：{str(e)}", "red")
            return None
    
    def _extract_data(self, content, url):
        """从单个URL的内容中提取邮箱、手机号和学号（自动去重）"""
        # 提取邮箱（自动去重）
        if self.email_var.get():
            self._log(f"[{url}] 正在提取邮箱（自动去重）...", "blue")
            # 第一步：单个URL内先去重
            email_list = set(re.findall(EMAIL_PATTERN, content, re.IGNORECASE))
            new_emails = email_list - self.all_email_results  # 仅新增未存在的邮箱
            if new_emails:
                self._log(f"[{url}] 提取到 {len(email_list)} 个邮箱，其中新增 {len(new_emails)} 个唯一邮箱：", "green")
                for email in new_emails:
                    self._log(f"  - {email}")
                self.all_email_results.update(new_emails)  # 合并到全局集合
            else:
                if email_list:
                    self._log(f"[{url}] 提取到 {len(email_list)} 个邮箱，但均为重复数据", "blue")
                else:
                    self._log(f"[{url}] 未提取到邮箱", "red")
        
        # 提取中国手机号（自动去重）
        if self.phone_var.get():
            self._log(f"[{url}] 正在提取手机号（自动去重）...", "blue")
            # 先匹配，再清洗格式（去掉+86、空格、-）
            raw_phones = re.findall(CHINA_PHONE_PATTERN, content)
            # 清洗手机号格式，统一为11位纯数字
            cleaned_phones = set()  # 单个URL内先去重
            for phone in raw_phones:
                clean_phone = re.sub(r'[^0-9]', '', phone)
                if len(clean_phone) == 11:
                    cleaned_phones.add(clean_phone)
                elif len(clean_phone) == 13 and clean_phone.startswith("86"):
                    cleaned_phones.add(clean_phone[2:])
        
            new_phones = cleaned_phones - self.all_phone_results  # 仅新增未存在的手机号
            if new_phones:
                self._log(f"[{url}] 提取到 {len(cleaned_phones)} 个手机号，其中新增 {len(new_phones)} 个唯一手机号：", "green")
                for phone in new_phones:
                    self._log(f"  - {phone}")
                self.all_phone_results.update(new_phones)  # 合并到全局集合
            else:
                if cleaned_phones:
                    self._log(f"[{url}] 提取到 {len(cleaned_phones)} 个手机号，但均为重复数据", "blue")
                else:
                    self._log(f"[{url}] 未提取到手机号", "red")
        
        # 提取学号（自动去重）
        if self.student_id_var.get():
            self._log(f"[{url}] 正在提取学号（自动去重）...", "blue")
            try:
                # 获取当前使用的学号正则
                current_pattern = self.custom_student_id_pattern.get().strip() or STUDENT_ID_PATTERN
                # 尝试编译正则表达式（再次验证，确保安全）
                re.compile(current_pattern)
                # 提取学号
                raw_student_ids = re.findall(current_pattern, content)
                # 单个URL内先去重
                student_id_list = set(raw_student_ids)
                new_student_ids = student_id_list - self.all_student_id_results  # 仅新增未存在的学号
                if new_student_ids:
                    self._log(f"[{url}] 提取到 {len(student_id_list)} 个学号，其中新增 {len(new_student_ids)} 个唯一学号：", "green")
                    for student_id in new_student_ids:
                        self._log(f"  - {student_id}")
                    self.all_student_id_results.update(new_student_ids)  # 合并到全局集合
                else:
                    if student_id_list:
                        self._log(f"[{url}] 提取到 {len(student_id_list)} 个学号，但均为重复数据", "blue")
                    else:
                        self._log(f"[{url}] 未提取到学号", "red")
            except re.error as e:
                self._log(f"[{url}] 学号正则表达式错误：{str(e)}", "red")
            except Exception as e:
                self._log(f"[{url}] 学号提取失败：{str(e)}", "red")
    
    def manual_dedupe(self):
        """手动触发去重（兜底）"""
        try:
            # 对现有结果强制去重（实际集合已自动去重，此为兜底）
            prev_email_count = len(self.all_email_results)
            prev_phone_count = len(self.all_phone_results)
            prev_student_id_count = len(self.all_student_id_results)
            
            # 集合转列表再转集合（兜底去重，实际无必要，仅给用户提示）
            self.all_email_results = set(self.all_email_results)
            self.all_phone_results = set(self.all_phone_results)
            self.all_student_id_results = set(self.all_student_id_results)
            
            self._log("\n===== 手动去重完成 =====", "green")
            self._log(f"邮箱：去重前 {prev_email_count} 个 → 去重后 {len(self.all_email_results)} 个", "green")
            self._log(f"手机号：去重前 {prev_phone_count} 个 → 去重后 {len(self.all_phone_results)} 个", "green")
            self._log(f"学号：去重前 {prev_student_id_count} 个 → 去重后 {len(self.all_student_id_results)} 个", "green")
        except Exception as e:
            self._log(f"手动去重失败：{str(e)}", "red")
            messagebox.showerror("错误", f"手动去重失败：{str(e)}")
    
    def start_scraping(self):
        """开始爬取流程（支持单URL/批量，全程自动去重）"""
        # 清空之前的结果
        self.clear_results()
        
        # 检查网络
        if not self._check_internet():
            messagebox.showerror("错误", "网络连接失败，请检查网络后重试")
            return
        
        # 检查爬取选项
        if not self.email_var.get() and not self.phone_var.get() and not self.student_id_var.get():
            messagebox.warning("提示", "请至少选择一项爬取内容（邮箱/手机号/学号）")
            return
        
        mode = self.mode_var.get()
        if mode == "single":
            # 单URL爬取
            url = self.url_var.get().strip()
            if not self._validate_url(url):
                messagebox.showerror("错误", "请输入有效的URL（如：https://www.example.com）")
                return
            self._log(f"开始单URL爬取（自动去重）：{url}", "blue")
            # 爬取内容
            content = self._scrape_content(url)
            if content:
                self._extract_data(content, url)
            self._log("\n===== 单URL爬取完成！最终去重结果 =====", "green")
            self._log(f"总计提取到 {len(self.all_email_results)} 个唯一邮箱", "green")
            self._log(f"总计提取到 {len(self.all_phone_results)} 个唯一手机号", "green")
            self._log(f"总计提取到 {len(self.all_student_id_results)} 个唯一学号", "green")
        
        else:
            # 批量URL爬取
            if not hasattr(self, "batch_file_path") or not self.current_urls:
                messagebox.showerror("错误", "请先选择有效的TXT文件（包含URL）")
                return
            self._log(f"开始批量爬取（自动去重），共 {len(self.current_urls)} 个URL", "blue")
            # 遍历每个URL
            for idx, url in enumerate(self.current_urls, 1):
                self._log(f"\n===== 处理第 {idx}/{len(self.current_urls)} 个URL：{url} =====", "blue")
                if not self._validate_url(url):
                    self._log(f"[{url}] URL格式无效，跳过", "red")
                    continue
                # 爬取内容
                content = self._scrape_content(url)
                if content:
                    self._extract_data(content, url)
            # 汇总结果
            self._log("\n===== 批量爬取完成！最终去重结果 =====", "green")
            self._log(f"总计提取到 {len(self.all_email_results)} 个唯一邮箱", "green")
            self._log(f"总计提取到 {len(self.all_phone_results)} 个唯一手机号", "green")
            self._log(f"总计提取到 {len(self.all_student_id_results)} 个唯一学号", "green")
    
    def save_results(self):
        """保存结果到文件夹（仅保存唯一的邮箱、手机号和学号）"""
        if not self.all_email_results and not self.all_phone_results and not self.all_student_id_results:
            messagebox.warning("提示", "暂无爬取结果可保存")
            return
        
        # 选择保存目录
        folder_path = filedialog.askdirectory(title="选择保存目录")
        if not folder_path:
            return
        
        # 创建文件夹
        save_folder = os.path.join(folder_path, "Output")
        if not os.path.exists(save_folder):
            os.makedirs(save_folder)
        
        # 保存邮箱（转列表排序，方便查看）
        if self.all_email_results:
            sorted_emails = sorted(list(self.all_email_results))
            email_file = os.path.join(save_folder, "unique_emails.txt")
            with open(email_file, "w", encoding="utf-8") as f:
                f.write("\n".join(sorted_emails))
            self._log(f"唯一邮箱结果已保存到：{email_file}", "green")
        
        # 保存手机号（转列表排序）
        if self.all_phone_results:
            sorted_phones = sorted(list(self.all_phone_results))
            phone_file = os.path.join(save_folder, "unique_china_phones.txt")
            with open(phone_file, "w", encoding="utf-8") as f:
                f.write("\n".join(sorted_phones))
            self._log(f"唯一手机号结果已保存到：{phone_file}", "green")
        
        # 保存学号（转列表排序）
        if self.all_student_id_results:
            sorted_student_ids = sorted(list(self.all_student_id_results))
            student_id_file = os.path.join(save_folder, "unique_student_ids.txt")
            with open(student_id_file, "w", encoding="utf-8") as f:
                f.write("\n".join(sorted_student_ids))
            self._log(f"唯一学号结果已保存到：{student_id_file}", "green")
        
        messagebox.showinfo("成功", f"去重后的结果已保存到：{save_folder}")
    
    def clear_results(self):
        """清空结果"""
        self.all_email_results = set()
        self.all_phone_results = set()
        self.all_student_id_results = set()
        self.current_urls = []
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete(1.0, tk.END)
        self.result_text.config(state=tk.DISABLED)
        # 重置文件标签
        if hasattr(self, "file_label"):
            self.file_label.config(text="未选择文件", foreground="gray")

if __name__ == "__main__":
    # 启动GUI
    root = tk.Tk()
    app = WebScraperGUI(root)
    root.mainloop()
