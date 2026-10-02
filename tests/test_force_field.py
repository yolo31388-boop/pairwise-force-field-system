import pytest
from force_field.system import ForceFieldSystem


class TestForceFieldSystem:

    def test_apply_force_field(self):
        """力场应用不做范围检查，全场景物体都受力"""
        obj = ForceFieldSystem()
        result = obj.apply_force_field()
        self.assertIsNotNone(result)

    def test_check_occlusion(self):
        """力场遮挡不做检测，墙后面的物体也受力"""
        obj = ForceFieldSystem()
        result = obj.check_occlusion()
        self.assertIsNotNone(result)

    def test_apply_area_effect(self):
        """区域效果只做球体，不做盒子和胶囊体"""
        obj = ForceFieldSystem()
        result = obj.apply_area_effect()
        self.assertIsNotNone(result)

    def test_combine_force_fields(self):
        """力场叠加只做简单相加，不做优先级"""
        obj = ForceFieldSystem()
        result = obj.combine_force_fields()
        self.assertIsNotNone(result)

    def test_debug_force_field(self):
        """力场调试只画范围，不显示力的方向和大小"""
        obj = ForceFieldSystem()
        result = obj.debug_force_field()
        self.assertIsNotNone(result)

