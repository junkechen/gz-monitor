// GZ安环监测 - 移动端常量（与桌面端 src/config.py / data_processor.py 对齐）

const String kBaseUrl = 'http://222.175.25.10:8006';

// AES-256-CBC（服务端前端 Security.EncryptAES 还原，v5.44 更正）
const String kAesKey = 'i7t483eitnweh6phbi0jemr965dhbr63'; // 32 字节
const String kAesIv = 'i7t483eitnweh6ph'; // 16 字节

// 内置企业账户（与桌面端 BUILTIN_ACCOUNTS 一致）
const List<Map<String, String>> kBuiltinAccounts = [
  {'name': '山东冠洲股份有限公司', 'password': 'Gzgfah@163.com'},
  {'name': '山东冠洲鼎鑫板材科技有限公司', 'password': 'Gzgfah@163.com'},
  {'name': '冠县恒润热电有限公司', 'password': 'Gzgfah@163.com'},
  {'name': '山东冠县冠锌金属材料科技有限公司', 'password': 'Gzgfah@163.com'},
  {'name': '聊城东舜涂料科技有限公司', 'password': 'lCdstl5289099@'},
];

// 监测代码 -> 显示名（与桌面端 CODE_TO_NAME 一致）
const Map<String, String> kCodeToName = {
  '316': '化学需氧量', '302': 'pH值', '494': '流量',
  '492': '废水流量', '311': '氨氮', '301': '水温', '495': '累计流量',
  '383': '非甲烷总烃', '525': '烟气温度', '210': '烟气流量',
  '209': '烟气含氧量', '220': '碳氢化合物总烃', '299': '甲烷',
  '211': '流速', '527': '烟气湿度', '526': '烟气压力',
  'SO2': '二氧化硫', 'NOx': '氮氧化物', 'PM': '颗粒物',
  '201': '二氧化硫', '203': '氮氧化物', '207': '颗粒物',
};

// subtype：51=废水，64=废气/VOCs
const String kWaterSubtype = '51';
const String kGasSubtype = '64';

// 各类排口默认查询参数代码（实时数据取不到时的兜底）
const List<String> kDefaultWaterCodes = ['316', '302', '494', '492', '311'];
const List<String> kDefaultGasCodes = ['383', '525', '210', '209'];

// 排放量主参数：废水=化学需氧量(316)，废气=非甲烷总烃(383)
const String kWaterEmissionCode = '316';
const String kGasEmissionCode = '383';

bool isWaterType(String subType) =>
    subType.contains('废水') || subType.contains('污水');

String subtypeCodeOf(String subType) =>
    isWaterType(subType) ? kWaterSubtype : kGasSubtype;

String? codeName(String code) => kCodeToName[code];
