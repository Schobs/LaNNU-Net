#!/bin/bash
#SBATCH --account=kale
#SBATCH --partition=kale
#SBATCH --nodes=1
#SBATCH --gpus-per-node=1
#SBATCH --mem=34G
#SBATCH --mail-user=ogavin1@sheffield.ac.uk
#SBATCH --mail-type=FAIL
#SBATCH --comment=unetr_model_test

export SLURM_EXPORT_ENV=ALL

module load Anaconda3/5.3.0
module load cuDNN/7.6.4.38-gcccuda-2019b
source activate my_env
srun python main.py --cfg "configs/configs_BSC_projects/ceph_oscar.yaml"