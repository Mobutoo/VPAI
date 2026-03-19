# ComfyUI Official Documentation

Scraped on 2026-03-19 from https://docs.comfy.org

## ComfyUI Official Documentation - ComfyUI

**Source:** https://docs.comfy.org/

Skip to main contentComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationGet StartedComfyUI Official DocumentationSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI Official DocumentationThe most powerful open source node-based application for generative AIGetting StartedDownload & InstallInstall ComfyUI on Windows, macOS, or LinuxFirst GenerationCreate your first AI-generated imageBasic ConceptsUnderstand workflows, nodes, and linksComfy HubDiscover the world’s top creators and workflowsLearn & TutorialsInterface GuideNavigate the ComfyUI interfaceTutorialsStep-by-step guides for common tasksBuilt-in NodesLearn about each node in ComfyUIDevelopment & ExtensionDevelopment GuideContribute to ComfyUI developmentCustom NodesCreate and publish custom nodesLocal APIIntegrate with local ComfyUI serverCloud APIRun workflows via ComfyUI Cloud APIGet HelpContact SupportGet help from our support teamAccount ManagementCreate, login, and manage your accountBilling SupportManage subscriptions and paymentsTroubleshootingResolve common issues and errorsCommunityJoin the ComfyUI communityAbout ComfyUIWritten by comfyanonymous and other contributors.ComfyUI is a node-based interface and inference engine for generative AIUsers can combine various AI models and operations through nodes to achieve highly customizable and controllable content generationComfyUI is completely open source and can run on your local deviceCtrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/get_started/introduction

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Kling Start-End Frame to Video - ComfyUI Built-in NodeGetting StartedWindows Desktop VersionCtrl+I

---

## Getting Started with AI Image Generation - ComfyUI

**Source:** https://docs.comfy.org/get_started/gettingstarted

Skip to main contentComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationGet StartedGetting Started with AI Image GenerationSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishOn this pageGet StartedGetting Started with AI Image GenerationCopy pageThis tutorial will guide you through your first image generation with ComfyUI, covering basic interface operations like workflow loading, model installation, and image generationCopy pageThis guide aims to help you understand ComfyUI’s basic operations and complete your first image generation. We’ll cover:

Loading example workflows

Loading from ComfyUI’s workflow templates
Loading from images with workflow metadata


Model installation guidance

Automatic model installation
Manual model installation
Using ComfyUI Manager for model installation


Completing your first text-to-image generation

​About Text-to-Image
Text-to-Image is a fundamental AI drawing feature that generates images from text descriptions. It’s one of the most commonly used functions in AI art generation. You can think of the process as telling your requirements (positive and negative prompts) to an artist (the drawing model), who will then create what you want. Detailed explanations about text-to-image will be covered in the Text to Image chapter.
​ComfyUI Text-to-Image Workflow Tutorial
​1. Launch ComfyUI
Make sure you’ve followed the installation guide to start ComfyUI and can successfully enter the ComfyUI interface. Alternatively, you can use Comfy Cloud to use ComfyUI without any installation.

If you have not installed ComfyUI, please choose a suitable version to install based on your device.
ComfyUI DesktopComfyUI Desktop currently supports standalone installation for Windows and MacOS (ARM), currently in Beta
Code is open source on Github
Because Desktop is always built based on the stable release, so the latest updates may take some time to experience for Desktop, if you want to always experience the latest version, please use the portable version or manual installationYou can choose the appropriate installation for your system and hardware below Windows MacOS(Apple Silicon) LinuxComfyUI Desktop (Windows) Installation GuideSuitable for Windows version with Nvidia GPUComfyUI Desktop (MacOS) Installation GuideSuitable for MacOS with Apple SiliconComfyUI Desktop currently has no Linux prebuilds, please visit the Manual Installation section to install ComfyUIComfyUI Portable (Windows)Portable version is a ComfyUI version that integrates an independent embedded Python environment, using the portable version you can experience the latest features, currently only supports Windows systemComfyUI Portable (Windows) Installation GuideSupports Windows ComfyUI version running on Nvidia GPUs or CPU-only, always use the latest commits and completely portable.Manual InstallationComfyUI Manual Installation GuideSupports all system types and GPU types (Nvidia, AMD, Intel, Apple Silicon, Ascend NPU, Cambricon MLU)
​2. Load Default Text-to-Image Workflow
ComfyUI usually loads the default text-to-image workflow automatically when launched. However, you can try different methods to load workflows to familiarize yourself with ComfyUI’s basic operations:
 Load from Workflow Template Load from Images with Metadata Load from workflow.jsonFollow the numbered steps in the image:
Click the Fit View button in the bottom right to ensure any loaded workflow isn’t hidden
Click the folder icon (workflows) in the sidebar
Click the Browse example workflows button at the top of the Workflows panel
Continue with:
Select the first default workflow Image Generation to load it
Alternatively, you can select Browse workflow templates from the workflow menuAll images generated by ComfyUI contain metadata including workflow information. You can load workflows by:
Dragging and dropping a ComfyUI-generated image into the interface
Using menu Workflows -> Open to open an image
Try loading the workflow using this example image:
ComfyUI workflows can be stored in JSON format. You can export workflows using menu Workflows -> Export.Try downloading and loading this example workflow:Download text-to-image.jsonAfter downloading, use menu Workflows -> Open to load the JSON file.
​3. Model Installation
Most ComfyUI installations don’t include base models by default. After loading the workflow, if you don’t have the v1-5-pruned-emaonly-fp16.safetensors model installed, you’ll see this prompt:

All models are stored in <your ComfyUI installation>/ComfyUI/models/ with subfolders like checkpoints, embeddings, vae, lora, upscale_model,

---

## Page Not Found

**Source:** https://docs.comfy.org/essentials/comfyui_server

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?ComfyUI Interface OverviewServer OverviewKling Text to Video - ComfyUI Built-in NodeCtrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/essentials/custom_node_overview

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Custom NodesCustom nodes (new UI)Custom Node CI/CD
      💬 Join the Discussion
      Comments could not be loaded at this time.
      Please first check if there are existing discussions about this page. If you can't find any relevant discussions, then start a new one to connect your comments with this page.
      
        Find Related Discussions
        Start New Discussion
      
    Ctrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/essentials/custom_node_basics

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Custom NodesCustom nodes (new UI)Custom Node CI/CD
      💬 Join the Discussion
      Comments could not be loaded at this time.
      Please first check if there are existing discussions about this page. If you can't find any relevant discussions, then start a new one to connect your comments with this page.
      
        Find Related Discussions
        Start New Discussion
      
    Ctrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/essentials/custom_node_datatypes

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Custom NodesCustom nodes (new UI)Custom Node CI/CD
      💬 Join the Discussion
      Comments could not be loaded at this time.
      Please first check if there are existing discussions about this page. If you can't find any relevant discussions, then start a new one to connect your comments with this page.
      
        Find Related Discussions
        Start New Discussion
      
    Ctrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/essentials/custom_node_images_and_masks

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Images, Latents, and MasksRecraft Image Inpainting - ComfyUI Native Node DocumentationMask Editor - Create and Edit Masks in ComfyUI
      💬 Join the Discussion
      Comments could not be loaded at this time.
      Please first check if there are existing discussions about this page. If you can't find any relevant discussions, then start a new one to connect your comments with this page.
      
        Find Related Discussions
        Start New Discussion
      
    Ctrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/essentials/custom_node_widgets_and_combos

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Custom nodes (new UI)Custom NodesManaging custom nodes with ComfyUI-Manager (legacy UI)Ctrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/essentials/custom_node_lifecycle

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?LifecycleCustom nodes (new UI)Custom Nodes
      💬 Join the Discussion
      Comments could not be loaded at this time.
      Please first check if there are existing discussions about this page. If you can't find any relevant discussions, then start a new one to connect your comments with this page.
      
        Find Related Discussions
        Start New Discussion
      
    Ctrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/essentials/custom_node_lazy_evaluation

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Lazy EvaluationExecution Model Inversion GuideV3 MigrationCtrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/essentials/custom_node_snippets

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Custom NodesCustom nodes (new UI)Custom Node CI/CD
      💬 Join the Discussion
      Comments could not be loaded at this time.
      Please first check if there are existing discussions about this page. If you can't find any relevant discussions, then start a new one to connect your comments with this page.
      
        Find Related Discussions
        Start New Discussion
      
    Ctrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/essentials/custom_node_tensors

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Custom nodes (new UI)Custom NodesCustom Node CI/CD
      💬 Join the Discussion
      Comments could not be loaded at this time.
      Please first check if there are existing discussions about this page. If you can't find any relevant discussions, then start a new one to connect your comments with this page.
      
        Find Related Discussions
        Start New Discussion
      
    Ctrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/essentials/custom_node_ui

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Custom nodes (new UI)Managing custom nodes with ComfyUI-Manager (legacy UI)Custom NodesCtrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/essentials/comms_messages

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?MessagesRoutesGetting StartedCtrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/tutorials/basic/text_to_image

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Recraft Text to Image - ComfyUI Built-in Node DocumentationLuma Text to Image - ComfyUI Native Node DocumentationLuma Image to Image - ComfyUI Built-in Node DocumentationCtrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/tutorials/basic/image_to_image

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Kling Image to Video (Camera Control) - ComfyUI Built-in NodeLuma Image to Image - ComfyUI Built-in Node DocumentationMiniMax Image to Video - ComfyUI Native Node Documentation
      💬 Join the Discussion
      Comments could not be loaded at this time.
      Please first check if there are existing discussions about this page. If you can't find any relevant discussions, then start a new one to connect your comments with this page.
      
        Find Related Discussions
        Start New Discussion
      
    Ctrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/tutorials/basic/inpainting

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Wan ATI ComfyUI Native Workflow TutorialWan-Alpha TutorialFlux.1 Krea Dev ComfyUI Workflow Tutorial
      💬 Join the Discussion
      Comments could not be loaded at this time.
      Please first check if there are existing discussions about this page. If you can't find any relevant discussions, then start a new one to connect your comments with this page.
      
        Find Related Discussions
        Start New Discussion
      
    Ctrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/tutorials/basic/upscaling

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Video upscaling in ComfyUIComfyUI Image Upscale WorkflowWan ATI ComfyUI Native Workflow TutorialCtrl+I

---

## ComfyUI LoRA Example - ComfyUI

**Source:** https://docs.comfy.org/tutorials/basic/lora

Skip to main contentComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationBasic ExamplesComfyUI LoRA ExampleSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesText to ImageImage to ImageInpaintOutpaintUpscaleLoRAMultiple LoRAsControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishOn this pageBasic ExamplesComfyUI LoRA ExampleCopy pageThis guide will help you understand and use a single LoRA modelCopy pageLoRA (Low-Rank Adaptation) is an efficient technique for fine-tuning large generative models like Stable Diffusion.
It introduces trainable low-rank matrices to the pre-trained model, adjusting only a portion of parameters rather than retraining the entire model,
thus achieving optimization for specific tasks at a lower computational cost.
Compared to base models like SD1.5, LoRA models are smaller and easier to train.

The image above compares generation with the same parameters using dreamshaper_8 directly versus using the blindbox_V1Mix LoRA model.
As you can see, by using a LoRA model, we can generate images in different styles without adjusting the base model.
We will demonstrate how to use a LoRA model. All LoRA variants: Lycoris, loha, lokr, locon, etc… are used in the same way.
In this example, we will learn how to load and use a LoRA model in ComfyUI, covering the following topics:

Installing a LoRA model
Generating images using a LoRA model
A simple introduction to the Load LoRA node

​Required Model Installation
Download the dreamshaper_8.safetensors file and put it in your ComfyUI/models/checkpoints folder.
Download the blindbox_V1Mix.safetensors file and put it in your ComfyUI/models/loras folder.
​LoRA Workflow File
Download the image below and drag it into ComfyUI to load the workflow.

Images containing workflow JSON in their metadata can be directly dragged into ComfyUI or loaded using the menu Workflows -> Open (ctrl+o).
​Complete the Workflow Step by Step
Follow the steps in the diagram below to ensure the workflow runs correctly.


Ensure Load Checkpoint loads dreamshaper_8.safetensors
Ensure Load LoRA loads blindbox_V1Mix.safetensors
Click the Queue button, or use the shortcut Ctrl(cmd) + Enter to generate the image

​Load LoRA Node Introduction

Models in the ComfyUI\models\loras folder will be detected by ComfyUI and can be loaded using this node.
​Input Types
Parameter NameFunctionmodelConnect to the base modelclipConnect to the CLIP modellora_nameSelect the LoRA model to load and usestrength_modelAffects how strongly the LoRA influences the model weights; higher values make the LoRA style strongerstrength_clipAffects how strongly the LoRA influences the CLIP text embeddings
​Output Types
Parameter NameFunctionmodelOutputs the model with LoRA adjustments appliedclipOutputs the CLIP model with LoRA adjustments applied
This node supports chain connections, allowing multiple Load LoRA nodes to be linked in series to apply multiple LoRA models. For more details, please refer to ComfyUI Multiple LoRAs Example

​Try It Yourself

Try modifying the prompt or adjusting different parameters of the Load LoRA node, such as strength_model, to observe changes in the generated images and become familiar with the Load LoRA node.
Visit CivitAI to download other kinds of LoRA models and try using them.

      
        💬
        💬 Click or scroll here to load comments
      
    Was this page helpful?YesNoSuggest editsRaise issueComfyUI Image Upscale WorkflowPreviousComfyUI Multiple LoRAs ExampleNextCtrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/tutorials/basic/controlnet

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?ComfyUI ControlNet Usage ExampleComfyUI Mixing ControlNet ExamplesComfyUI Wan2.2 Fun Camera Control: Video Generation Workflow Example
      💬 Join the Discussion
      Comments could not be loaded at this time.
      Please first check if there are existing discussions about this page. If you can't find any relevant discussions, then start a new one to connect your comments with this page.
      
        Find Related Discussions
        Start New Discussion
      
    Ctrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/tutorials/api/getting_started

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Dialog APIOpenAPI SpecificationComfyUI Account API Key IntegrationCtrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/tutorials/api/websocket

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Dialog APIOpenAPI SpecificationJavascript ExtensionsCtrl+I

---

## Page Not Found

**Source:** https://docs.comfy.org/tutorials/api/run_workflow

Skip to main contentSearch...Ctrl KGet StartedIntroductionInstall locallyComfy CloudInstall Custom NodesFirst GenerationBasic ConceptsWorkflowNodesCustom NodesPropertiesLinksModelsDependenciesInterface GuideInterface OverviewAPP modeNodes 2.0Mask EditorWorkflow TemplatesSubgraphPartial ExecutionNode docsComfyUI SettingsComfyUI-ManagerTutorialsBasic ExamplesControlNetImage3DVideoAudioUtilityPartner NodesChangelogEnglishComfyUI home pageGet StartedBuilt-in NodesDevelopmentSupportRegistry API ReferenceCloud API ReferenceSearch...NavigationPage Not Found404Page Not FoundWe couldn't find the page. Maybe you were looking for one of these pages below?Partial Execution - Run Only Part of Your workflow in ComfyUISubmit a workflow for executionWan ATI ComfyUI Native Workflow TutorialCtrl+I

---

