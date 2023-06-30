from numpy.random import uniform as U
from placement.factory import AssetFactory, make_asset_collection
from placement.instance_scatter import scatter_instances
from surfaces.scatters.chopped_trees import approx_settle_transform
def apply(obj, n=5, selection=None):
    pinecones = make_asset_collection(
        factories, n=n, verbose=True,
        weights=np.random.uniform(0.5, 1, len(factories)))
    
    for o in pinecones.objects:
        approx_settle_transform(o, samples=30)
    d = np.deg2rad(90)
    ar = np.deg2rad(20)
    scatter_obj = scatter_instances(
        vol_density=U(0.05, 0.25), min_spacing=0.05,
        rotation_offset=lambda nw: nw.uniform((d-ar, -ar, -ar), (d+ar, ar, ar)),
        scale=U(0.05, 0.8), scale_rand=U(0.2, 0.8), scale_rand_axi=U(0, 0.1),
