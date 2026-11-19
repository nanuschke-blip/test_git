from setuptools import find_packages, setup

package_name = 'm1_projection'

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
    description='M1-3: TF tree, approximate time sync and laser-to-image projection',
    license='Apache-2.0',
    extras_require={'test': ['pytest']},
    entry_points={
        'console_scripts': [
            'projection_node = m1_projection.projection_node:main',
            'slop_sweep = m1_projection.slop_sweep:main',
        ],
    },
)
