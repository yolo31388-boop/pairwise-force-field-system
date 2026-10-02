"""
pairwise-force-field-system - ForceFieldSystem

This module contains a deliberately broken implementation.
Fix all bugs so that tests pass.
"""


class ForceFieldSystem:
    def __init__(self):
        self.state = {}

    def apply_force_field(self, *args, **kwargs):
        """BUG: 力场应用不做范围检查，全场景物体都受力"""
        return None

    def check_occlusion(self, *args, **kwargs):
        """BUG: 力场遮挡不做检测，墙后面的物体也受力"""
        return None

    def apply_area_effect(self, *args, **kwargs):
        """BUG: 区域效果只做球体，不做盒子和胶囊体"""
        return None

    def combine_force_fields(self, *args, **kwargs):
        """BUG: 力场叠加只做简单相加，不做优先级"""
        return None

    def debug_force_field(self, *args, **kwargs):
        """BUG: 力场调试只画范围，不显示力的方向和大小"""
        return None

