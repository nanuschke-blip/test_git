import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'm1_launch'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        (os.path.join('share', package_name, 'params'), glob('params/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='car',
    maintainer_email='314140205+nanuschke-blip@users.noreply.github.com',
    description='M1-2 Launch orchestration: namespaces, YAML params, ordering',
    license='Apache-2.0',
    extras_require={'test': ['pytest']},
    entry_points={
        'console_scripts': [
            'node_a = m1_launch.node_a_sensor:main',
            'node_b = m1_launch.node_b_filter:main',
            'node_c = m1_launch.node_c_alarm:main',
        ],
    },
)
