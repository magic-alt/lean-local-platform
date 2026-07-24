# Browser evidence

应用内 Browser 插件返回 `No browser is available`，记录为
`ENVIRONMENT_BLOCKED`。随后使用仓库自带 Chromium Playwright 直接访问正式
Compose UI/API（禁用测试栈和 seed）：修复 API helper runtime token 支持前
5 passed/1 failed，修复后 6 passed。

这只覆盖现有 smoke/resilience/docs，不覆盖用户要求的 20 个完整 Level 5 场景。
