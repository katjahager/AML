import argparse
import transformers
import os
import json
import torch
import logging

from src.models import models
from src.runners.intrasentence_inference_runner import IntrasentenceInferenceRunner
from src.runners.intersentence_inference_runner import IntersentenceInferenceRunner
from src.utils import utils

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")

def parse_args():
    parser = argparse.ArgumentParser(description="Run Intrasentence and Intersentence inference on StereoSet.")
    parser.add_argument(
        "--top-level-dir",
        type=str,
        default=os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..")),
        help="Top-level directory of the repository.",
    )
    parser.add_argument(
        "--intrasentence-model",
        type=str,
        default="BertForMLM",
        choices=[
            "BertForMLM",
            "SwissBertForMLM"
        ],
        help="Architecture to use for the intrasentence inference.",
    )
    parser.add_argument(
        "--intersentence-model",
        type=str,
        default="BertForNSP",
        choices=[
            "BertForNSP",
            "SwissBertForNSP"
        ],
        help="Architecture to use for the intersentence inference.",
    )
    parser.add_argument(
        "--pretrained-model-name",
        type=str,
        default="bert-base-uncased",
        choices=["bert-base-uncased", "ZurichNLP/swissbert-xlm-vocab"],
        help="Pretrained model name from which architecture weights are loaded.",
    )
    parser.add_argument(
        "--eraser-path-list",
        type=str,
        nargs='*',
        action=utils.customAction,
        dest='eraser_path_list',
        const=['default_path'],
        help="List of paths to pickle files of trained concept erasure models.",
    )
    parser.add_argument(
        "--eraser-before-lang-adapt",
        default=False,
        action="store_true",
        help="Boolean flag to indicate if concept erasure model should be applied before language adapters of last layer.",
    )
    parser.add_argument(
        "--ckpt-path",
        type=str,
        default=None,
        help="Path to debiased model checkpoint from which architecture weights are loaded.",
    )
    parser.add_argument(
        "--intrasentence-data-path",
        type=str,
        default=None,
        help="Path to intrasentence data file.",
    )
    parser.add_argument(
        "--intersentence-data-path",
        type=str,
        default=None,
        help="Path to intersentence data file.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Batch size to use during inference.",
    )
    parser.add_argument(
        "--tiny-eval-frac",
        type=float,
        nargs='?',
        const=0.1,
        help="Fraction of the dataset to use for evaluation.",
    )
    parser.add_argument(
        "--softmax-temperature",
        type=float,
        default=1.0,
        help="Temperature to use for softmax.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Path to save inference results.",
    )
    parser.add_argument(
        "--logging-dir",
        type=str,
        default=None,
        help="Path to save logs.",
    )
    parser.add_argument(
        "--skip-intrasentence",
        action="store_true",
        help="Do not perform intrasentence inference.",
    )
    parser.add_argument(
        "--skip-intersentence",
        default=True,
        action="store_true",
        help="Do not perform intersentence inference.",
    )
    parser.add_argument(
        "--experiment-id",
        type=str,
        default=None,
        help="ID of the experiment.",
    )
    return parser.parse_args()


def main(args):
    logger.info("############# STARTED #############")
    logger.info(f"Args provided: {args}")
    logger.info(f"Using torch device: {DEVICE}")

    if args.intrasentence_data_path is None:
        intrasentence_data_path = os.path.join(args.top_level_dir, "data/df_intrasentence_en.pkl")
    else:
        intrasentence_data_path = args.intrasentence_data_path
    if args.intersentence_data_path is None:
        intersentence_data_path = os.path.join(args.top_level_dir, "data/df_intersentence_en.pkl")
    else:
        intersentence_data_path = args.intersentence_data_path
    if args.output_dir is None:
        output_dir = os.path.join(args.top_level_dir, "inference_output")
    else:
        output_dir = args.output_dir
    if args.eraser_path_list == ['default_path']:
        eraser_path_list = [os.path.join(args.top_level_dir, "data/concept_eraser/eraser_models/eraser.pkl")]
    else:
        eraser_path_list = args.eraser_path_list


    os.makedirs(output_dir, exist_ok=True)

    combined_results = {}

    tokenizer = transformers.AutoTokenizer.from_pretrained(args.pretrained_model_name, use_fast=True)
    if not args.skip_intrasentence:
        lang = intrasentence_data_path.split("/")[-1].split("_")[-1].split(".")[0]
        intrasentence_model = getattr(models, args.intrasentence_model)(args.ckpt_path or args.pretrained_model_name, lang, eraser_path_list, args.eraser_before_lang_adapt)
        intrasentence_runner = IntrasentenceInferenceRunner(intrasentence_model,
                                                            tokenizer,
                                                            intrasentence_data_path,
                                                            args.pretrained_model_name,                                                        
                                                            args.batch_size,
                                                            args.tiny_eval_frac,
                                                            args.softmax_temperature)
        intrasentence_results = intrasentence_runner.run()
        combined_results["intrasentence"] = intrasentence_results
        
        with open(os.path.join(output_dir, f'intrasentence_{args.intrasentence_model}{"_debiased" if args.ckpt_path else ""}_{lang}{("_" + args.experiment_id) if args.experiment_id else ""}{("_eraser") if args.eraser_path_list else ""}.json'), "w") as f:
            json.dump(intrasentence_results, f, indent=2)
        
    if not args.skip_intersentence:
        lang = intersentence_data_path.split("/")[-1].split("_")[-1].split(".")[0]
        intersentence_model = getattr(models, args.intersentence_model)(args.ckpt_path or args.pretrained_model_name, lang, eraser_path_list, args.eraser_before_lang_adapt)
        intersentence_runner = IntersentenceInferenceRunner(intersentence_model,
                                                            tokenizer,
                                                            intersentence_data_path,
                                                            args.pretrained_model_name,                                                        
                                                            args.batch_size,
                                                            args.tiny_eval_frac,
                                                            args.softmax_temperature)
        intersentence_results = intersentence_runner.run()
        combined_results["intersentence"] = intersentence_results

        with open(os.path.join(output_dir, f'intersentence_{args.intersentence_model}{"_debiased" if args.ckpt_path else ""}_{lang}{("_" + args.experiment_id) if args.experiment_id else ""}{("_eraser") if args.eraser_path_list else ""}.json'), "w") as f:
            json.dump(intersentence_results, f, indent=2)
    
    with open(os.path.join(output_dir, f'combined_results{"_" + args.intrasentence_model if not args.skip_intrasentence else ""}{"_" + args.intersentence_model if not args.skip_intersentence else ""}{"_debiased" if args.ckpt_path else ""}_{lang}{("_" + args.experiment_id) if args.experiment_id else ""}{("_eraser") if args.eraser_path_list else ""}.json'), "w") as f:
        json.dump(combined_results, f, indent=2)


    logger.info("############# FINISHED #############")



if __name__ == "__main__":
    args = parse_args()

    if args.logging_dir is None:
        logging_dir = os.path.join(args.top_level_dir, "logs")
    else:
        logging_dir = args.logging_dir
    os.makedirs(logging_dir, exist_ok=True)
    logging.basicConfig(filename=os.path.join(logging_dir, "inference_runs.log"),
                        format='%(asctime)s - %(name)s - %(message)s',
                        level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    main(args)