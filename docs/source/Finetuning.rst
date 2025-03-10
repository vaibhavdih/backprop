.. _ft:

Finetuning
==========

Finetuning lets you take a model that has been trained on a very broad task and adapt it to your specific niche.

Basic Example
^^^^^^^^^^^^^

Here is a simple example of finetuning for text generation with T5.

.. code-block:: python

    from backprop.models import T5
    from backprop import TextGeneration

    tg = TextGeneration(T5)

    # Any text works as training data
    inp = ["I really liked the service I received!", "Meh, it was not impressive."]
    out = ["positive", "negative"]
    params = {"input_text": inp, "output_text": out}

    # Finetune with a single line of code
    tg.finetune(params)

    # Use your trained model
    prediction = tg("I enjoyed it!")


In-depth Example
^^^^^^^^^^^^^^^^    

See the in-depth `Getting Started with Finetuning <https://github.com/backprop-ai/backprop/blob/main/examples/Finetuning_GettingStarted.ipynb>`_ notebook with code.

Supported tasks and models
^^^^^^^^^^^^^^^^^^^^^^^^^^

Text Generation
---------------

References:

* :ref:`text-generation task <text-generation>`
* `text-generation finetuning notebook <https://github.com/backprop-ai/backprop/blob/main/examples/Finetuning_TextGeneration.ipynb>`_

Supported models:

* :ref:`T5 <t5>`
* :ref:`T5QASummaryEmotion <t5baseqasummaryemotion>`
  
Image Classification
--------------------

References:

* :ref:`image-classification task <image-classification>`
* `image-classification finetuning notebook <https://github.com/backprop-ai/backprop/blob/main/examples/Finetuning_ImageClassification.ipynb>`_

Supported models:

* :ref:`EfficientNet <efficientnet>`

Text Classification
-------------------

References:

* :ref:`text-classification task <text-classification>`
* `text-classification finetuning notebook <https://github.com/backprop-ai/backprop/blob/main/examples/Finetuning_TextClassification.ipynb>`_

Supported models:

* :ref:`XLNet <xlnet>`

Text Vectorisation
-------------------

References:

* :ref:`text-vectorisation task <text-vectorisation>`
* `text-vectorisation finetuning notebook <https://github.com/backprop-ai/backprop/blob/main/examples/Finetuning_TextVectorisation.ipynb>`_

Supported models:

* :ref:`DistiluseBaseMultilingualCasedV2 <distiluse>`
* :ref:`MSMARCODistilrobertaBaseV2 <distilroberta-msmarco>`


