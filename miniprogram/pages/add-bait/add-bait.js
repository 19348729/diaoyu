const api = require('../../utils/api');

// 经典单品配置库 (用于下拉与自动填充)
const BAIT_DB = {
  '老鬼': [
    { name: '九一八野战篇', flavor: '纯香', targetFish: '综合' },
    { name: '速攻2号', flavor: '状态调整', targetFish: '综合' },
    { name: '螺鲤2号', flavor: '浓腥', targetFish: '鲤鱼' },
    { name: '螺鲤3号', flavor: '酵香', targetFish: '鲤鱼' },
    { name: '狂龙鲫', flavor: '香腥', targetFish: '鲫鱼' },
  ],
  '龙王恨': [
    { name: '野战蓝鲫', flavor: '腥香', targetFish: '综合' },
    { name: '大蓝鲫', flavor: '腥香', targetFish: '综合' },
    { name: '蓝鲫X5', flavor: '香腥', targetFish: '综合' }
  ],
  '化氏': [
    { name: '大板鲫', flavor: '纯香', targetFish: '鲫鱼' },
    { name: '4号鲫', flavor: '腥香', targetFish: '鲫鱼' },
    { name: '6号鲫', flavor: '浓腥', targetFish: '鲫鱼' },
    { name: '钢弹', flavor: '香腥', targetFish: '综合' }
  ],
  '天元': [
    { name: '大毛鲫', flavor: '纯香', targetFish: '鲫鱼' },
    { name: '红魔', flavor: '浓腥', targetFish: '综合' }
  ],
  '西部风': [
    { name: '老坛玉米', flavor: '发酵', targetFish: '综合' },
    { name: '牛B鲫', flavor: '奶香', targetFish: '鲫鱼' }
  ],
  '钓鱼王': [
    { name: '疯钓鲫', flavor: '本味', targetFish: '鲫鱼' }
  ],
  '自然饵': [
    { name: '红虫', flavor: '浓腥', targetFish: '综合' },
    { name: '蚯蚓', flavor: '浓腥', targetFish: '综合' },
    { name: '嫩玉米', flavor: '纯香', targetFish: '草鱼' },
    { name: '老玉米', flavor: '发酵', targetFish: '鲤鱼' },
    { name: '麦粒', flavor: '本味', targetFish: '鲫鱼' }
  ]
};

Page({
  data: {
    editId: '',
    
    // 选项数据
    categoryOptions: ['商品饵', '自然饵/活饵', '状态辅料', '小药/添加剂'],
    brandOptions: ['老鬼', '龙王恨', '化氏', '天元', '西部风', '钓鱼王', '其他/自定义'],
    flavorOptions: ['腥香', '香腥', '浓腥', '纯香', '麦香', '奶香', '果酸', '薯香', '肝味', '发酵', '本味', '状态调整', '其他'],
    targetFishOptions: ['综合', '鲫鱼', '鲤鱼', '草鱼', '鲢鳙', '罗非', '其他'],

    // 当前选中的索引
    categoryIndex: -1,
    brandIndex: -1,
    flavorIndex: -1,
    targetFishIndex: -1,

    // 名称与品牌联动相关
    isCustomBrand: false,
    customBrand: '',
    
    useNamePicker: false,
    nameOptions: [],
    nameIndex: -1,
    baitName: '', // 当不使用 picker 时的自定义名称

    showAutoFillTip: false
  },

  onLoad(options) {
    if (options.id) {
      this.setData({ editId: options.id });
      this.loadBaitDetail(options.id);
    }
  },

  loadBaitDetail(id) {
    wx.showLoading({ title: '加载中...' });
    api.getUserBait(id)
      .then((res) => {
        wx.hideLoading();
        if (res.status === 'ok' && res.data) {
          const b = res.data;
          
          const catIdx = this.data.categoryOptions.indexOf(b.category);
          let brandIdx = this.data.brandOptions.indexOf(b.brand);
          let isCustomBrand = false;
          let customBrand = '';

          // 如果品牌不在列表中，设置为自定义
          if (b.category !== '自然饵/活饵' && brandIdx === -1) {
            brandIdx = this.data.brandOptions.length - 1; // 选定 "其他/自定义"
            isCustomBrand = true;
            customBrand = b.brand;
          }

          const flavIdx = this.data.flavorOptions.indexOf(b.flavor);
          const fishIdx = this.data.targetFishOptions.indexOf(b.targetFish);

          this.setData({
            categoryIndex: catIdx >= 0 ? catIdx : 0,
            brandIndex: brandIdx >= 0 ? brandIdx : -1,
            isCustomBrand,
            customBrand,
            baitName: b.name,
            flavorIndex: flavIdx >= 0 ? flavIdx : -1,
            targetFishIndex: fishIdx >= 0 ? fishIdx : -1,
            useNamePicker: false // 编辑时默认进入手填模式，避免下拉列表没对上
          });
        }
      })
      .catch((err) => {
        wx.hideLoading();
        console.error('[AddBait] 获取详情失败:', err);
      });
  },

  onCategoryChange(e) {
    const idx = parseInt(e.detail.value);
    const cat = this.data.categoryOptions[idx];
    
    let updates = {
      categoryIndex: idx,
      brandIndex: -1,
      isCustomBrand: false,
      customBrand: '',
      useNamePicker: false,
      nameOptions: [],
      nameIndex: -1,
      baitName: '',
      showAutoFillTip: false
    };

    // 自然饵特殊处理：不需要选品牌，直接给经典自然饵下拉
    if (cat === '自然饵/活饵') {
      const dbList = BAIT_DB['自然饵'];
      updates.useNamePicker = true;
      updates.nameOptions = dbList.map(item => item.name).concat(['其他/自定义']);
    }

    this.setData(updates);
  },

  onBrandChange(e) {
    const idx = parseInt(e.detail.value);
    const brand = this.data.brandOptions[idx];
    
    let isCustom = (brand === '其他/自定义');
    
    let updates = {
      brandIndex: idx,
      isCustomBrand: isCustom,
      useNamePicker: false,
      nameOptions: [],
      nameIndex: -1,
      baitName: '',
      showAutoFillTip: false
    };

    if (!isCustom && BAIT_DB[brand]) {
      // 从库里提取热销单品
      updates.useNamePicker = true;
      updates.nameOptions = BAIT_DB[brand].map(item => item.name).concat(['其他/自定义']);
    }

    this.setData(updates);
  },

  onCustomBrandInput(e) {
    this.setData({ customBrand: e.detail.value });
  },

  onNamePickerChange(e) {
    const idx = parseInt(e.detail.value);
    const nameStr = this.data.nameOptions[idx];
    
    if (nameStr === '其他/自定义') {
      this.setData({
        nameIndex: -1,
        useNamePicker: false,
        baitName: '',
        showAutoFillTip: false
      });
      return;
    }

    // 尝试寻找自动补全配置
    let autoConfig = null;
    const { categoryIndex, brandIndex, brandOptions, categoryOptions } = this.data;
    const cat = categoryOptions[categoryIndex];
    
    if (cat === '自然饵/活饵') {
      autoConfig = BAIT_DB['自然饵'].find(x => x.name === nameStr);
    } else {
      const brand = brandOptions[brandIndex];
      if (BAIT_DB[brand]) {
        autoConfig = BAIT_DB[brand].find(x => x.name === nameStr);
      }
    }

    let updates = {
      nameIndex: idx,
      baitName: nameStr,
      showAutoFillTip: false
    };

    // 智能防呆：自动装配味型与目标鱼
    if (autoConfig) {
      const fIdx = this.data.flavorOptions.indexOf(autoConfig.flavor);
      const tfIdx = this.data.targetFishOptions.indexOf(autoConfig.targetFish);
      
      if (fIdx >= 0) updates.flavorIndex = fIdx;
      if (tfIdx >= 0) updates.targetFishIndex = tfIdx;
      updates.showAutoFillTip = true;
    }

    this.setData(updates);
  },

  onNameInput(e) {
    this.setData({ baitName: e.detail.value });
  },

  onFlavorChange(e) {
    this.setData({ flavorIndex: parseInt(e.detail.value) });
  },

  onTargetFishChange(e) {
    this.setData({ targetFishIndex: parseInt(e.detail.value) });
  },

  saveBait() {
    const { 
      editId, categoryIndex, categoryOptions,
      brandIndex, brandOptions, isCustomBrand, customBrand,
      baitName, flavorIndex, flavorOptions,
      targetFishIndex, targetFishOptions 
    } = this.data;

    if (categoryIndex < 0) return wx.showToast({ title: '请选择大类', icon: 'none' });
    
    const category = categoryOptions[categoryIndex];
    let brand = '自然饵'; // 自然饵大类的默认品牌名

    if (category !== '自然饵/活饵') {
      if (brandIndex < 0) return wx.showToast({ title: '请选择品牌', icon: 'none' });
      brand = isCustomBrand ? customBrand.trim() : brandOptions[brandIndex];
      if (!brand) return wx.showToast({ title: '请输入品牌', icon: 'none' });
    }

    if (!baitName.trim()) return wx.showToast({ title: '请输入饵料名称', icon: 'none' });
    if (flavorIndex < 0) return wx.showToast({ title: '请选择味型', icon: 'none' });
    if (targetFishIndex < 0) return wx.showToast({ title: '请选择目标鱼', icon: 'none' });

    const payload = {
      category,
      brand,
      name: baitName.trim(),
      flavor: flavorOptions[flavorIndex],
      target_fish: targetFishOptions[targetFishIndex]
    };

    wx.showLoading({ title: '保存中...' });
    const reqPromise = editId ? api.updateUserBait(editId, payload) : api.addUserBait(payload);

    reqPromise
      .then((res) => {
        wx.hideLoading();
        if (res.status === 'ok') {
          wx.showToast({ title: '保存成功', icon: 'success' });
          const pages = getCurrentPages();
          const prevPage = pages[pages.length - 2];
          if (prevPage && prevPage.loadUserInventory) {
            prevPage.loadUserInventory();
          }
          setTimeout(() => wx.navigateBack(), 1500);
        } else {
          wx.showToast({ title: res.message || '保存失败', icon: 'none' });
        }
      })
      .catch((err) => {
        wx.hideLoading();
        wx.showToast({ title: '网络错误', icon: 'none' });
      });
  }
});
