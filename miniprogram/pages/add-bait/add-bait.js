const api = require('../../utils/api');

Page({
  data: {
    editId: '',
    
    // 选项数据
    categoryOptions: ['商品饵', '自然饵/活饵', '状态辅料', '小药/添加剂'],
    brandOptions: [], // 动态拉取填充
    flavorOptions: ['腥香', '香腥', '浓腥', '纯香', '麦香', '奶香', '果酸', '薯香', '肝味', '发酵', '本味', '状态调整', '酸甜', '螺香', '酵香', '蜜香', '中药香', '浓甜奶香', '香草奶香', '蒜香', '复合香', '鲜腥', '其他'],
    targetFishOptions: ['综合', '鲫鱼', '鲤鱼', '草鱼', '青鱼', '鲢鳙', '罗非', '其他'],

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

  publicBaits: null, // 缓存在内存中的公共标准库数据

  onLoad(options) {
    wx.showLoading({ title: '加载标准库...' });
    api.getPublicBaits()
      .then((res) => {
        wx.hideLoading();
        if (res.status === 'ok' && res.data) {
          this.publicBaits = res.data;
        }
        
        // 如果是编辑模式，加载已有详情
        if (options.id) {
          this.setData({ editId: options.id });
          this.loadBaitDetail(options.id);
        }
      })
      .catch((err) => {
        wx.hideLoading();
        console.error('[AddBait] 获取标准库失败:', err);
        // 兜底进入编辑详情加载
        if (options.id) {
          this.setData({ editId: options.id });
          this.loadBaitDetail(options.id);
        }
      });
  },

  loadBaitDetail(id) {
    wx.showLoading({ title: '加载中...' });
    api.getUserBait(id)
      .then((res) => {
        wx.hideLoading();
        if (res.status === 'ok' && res.data) {
          const b = res.data;
          
          const catIdx = this.data.categoryOptions.indexOf(b.category);
          
          // 动态计算该分类下的品牌列表
          let brandOptions = [];
          if (this.publicBaits && this.publicBaits[b.category]) {
            brandOptions = Object.keys(this.publicBaits[b.category]).concat(['其他/自定义']);
          } else {
            brandOptions = ['其他/自定义'];
          }

          let brandIdx = brandOptions.indexOf(b.brand);
          let isCustomBrand = false;
          let customBrand = '';

          // 如果品牌不在列表中，设置为自定义
          if (brandIdx === -1) {
            brandIdx = brandOptions.length - 1; // 选定 "其他/自定义"
            isCustomBrand = true;
            customBrand = b.brand;
          }

          const flavIdx = this.data.flavorOptions.indexOf(b.flavor);
          const fishIdx = this.data.targetFishOptions.indexOf(b.targetFish);

          this.setData({
            categoryIndex: catIdx >= 0 ? catIdx : 0,
            brandOptions: brandOptions,
            brandIndex: brandIdx >= 0 ? brandIdx : -1,
            isCustomBrand,
            customBrand,
            baitName: b.name,
            flavorIndex: flavIdx >= 0 ? flavIdx : -1,
            targetFishIndex: fishIdx >= 0 ? fishIdx : -1,
            useNamePicker: false // 编辑时默认进入手填模式，避免数据脱节
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
    
    // 动态计算该分类下的品牌
    let brandOptions = [];
    if (this.publicBaits && this.publicBaits[cat]) {
      brandOptions = Object.keys(this.publicBaits[cat]).concat(['其他/自定义']);
    } else {
      brandOptions = ['其他/自定义'];
    }
    
    this.setData({
      categoryIndex: idx,
      brandOptions: brandOptions,
      brandIndex: -1,
      isCustomBrand: false,
      customBrand: '',
      useNamePicker: false,
      nameOptions: [],
      nameIndex: -1,
      baitName: '',
      showAutoFillTip: false
    });
  },

  onBrandChange(e) {
    const idx = parseInt(e.detail.value);
    const brand = this.data.brandOptions[idx];
    const cat = this.data.categoryOptions[this.data.categoryIndex];
    
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

    // 动态获取该品牌下的所有经典单品
    if (!isCustom && this.publicBaits && this.publicBaits[cat] && this.publicBaits[cat][brand]) {
      const dbList = this.publicBaits[cat][brand];
      updates.useNamePicker = true;
      updates.nameOptions = dbList.map(item => item.name).concat(['其他/自定义']);
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
    const { categoryIndex, categoryOptions, brandIndex, brandOptions } = this.data;
    const cat = categoryOptions[categoryIndex];
    const brand = brandOptions[brandIndex];
    
    let autoConfig = null;
    if (this.publicBaits && this.publicBaits[cat] && this.publicBaits[cat][brand]) {
      autoConfig = this.publicBaits[cat][brand].find(x => x.name === nameStr);
    }

    let updates = {
      nameIndex: idx,
      baitName: nameStr,
      showAutoFillTip: false
    };

    // 智能防呆：从公共库自动提取味型与目标鱼并渲染
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
