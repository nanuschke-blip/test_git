from setuptools import find_packages, setup

package_name = 'm1_nodes'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='car',
    maintainer_email='314140205+nanuschke-blip@users.noreply.github.com',
    description='M1-1 three-node chain (sensor / filter / alarm)',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
        entry_points={
        'console_scripts': [
            'node_a = m1_nodes.node_a_sensor:main',
            'node_b = m1_nodes.node_b_filter:main',
            'node_c = m1_nodes.node_c_alarm:main',
            'alarm_server = m1_nodes.node_c_server:main',
        ],
    },
)
