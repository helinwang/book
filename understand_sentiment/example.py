# 下载以及preprocess数据被封装到imdb这个模块里。不再需要执行两个命令处理数据。
from paddle.datasets import imdb
import paddle.model

from paddle.trainer_config_helpers import *

# stacked_lstm_net函数只负责构造网络结构(不包含data layer以及cost layer)，所以不负责区分是不是predict。
def stacked_lstm_net(data,
                     class_dim,
                     emb_dim=128,
                     hid_dim=512,
                     stacked_num=3):
    assert stacked_num % 2 == 1
    layer_attr = ExtraLayerAttribute(drop_rate=0.5)
    fc_para_attr = ParameterAttribute(learning_rate=1e-3)
    lstm_para_attr = ParameterAttribute(initial_std=0., learning_rate=1.)
    para_attr = [fc_para_attr, lstm_para_attr]
    bias_attr = ParameterAttribute(initial_std=0., l2_rate=0.)
    relu = ReluActivation()
    linear = LinearActivation()

    emb = embedding_layer(input=data_layer, size=emb_dim)
    fc1 = fc_layer(input=emb, size=hid_dim, act=linear, bias_attr=bias_attr)
    lstm1 = lstmemory(
        input=fc1, act=relu, bias_attr=bias_attr, layer_attr=layer_attr)

    inputs = [fc1, lstm1]
    for i in range(2, stacked_num + 1):
        fc_param = fc.param # 对layer引入param这个成员变量代表需要训练的权重。
        fc = fc_layer(
            input=inputs,
            size=hid_dim,
            act=linear,
            param_attr=para_attr,
            bias_attr=bias_attr)
        fc.param.b = fc_param.b # 所有的fc layer共享bias这个parameter，这个例子用来说明共享parameter的方法。

        lstm_param = lstm.param
        lstm = lstmemory(
            input=fc,
            reverse=(i % 2) == 0,
            act=relu,
            bias_attr=bias_attr,
            layer_attr=layer_attr)
        lstm.param = lstm_param # 所有的lstm共享所有的参数。
        inputs = [fc, lstm]
    fc_last = pooling_layer(input=inputs[0], pooling_type=MaxPooling())
    lstm_last = pooling_layer(input=inputs[1], pooling_type=MaxPooling())
    output = fc_layer(
        input=[fc_last, lstm_last],
        size=class_dim,
        act=SoftmaxActivation(),
        bias_attr=bias_attr,
        param_attr=para_attr)
    return output

is_predict = get_config_arg('is_predict', bool, False)

dict_dim = len(open("dict.txt").readlines())

# 本来class_dim是根据labels.list的行数确定的，这个文件的内容是:
# neg	0
# pos	1
# 我觉得我们并不需要有labels.list这个文件，所有的label默认都从0开始。class_dim-1结束。
# 交给用户自己来把neg和pos翻译成0和1。predict出来的0和1也由用户自己翻译回去。
class_dim = 2

data = data_layer("word", dict_dim)
output = stacked_lstm_net(data, class_dim)

# TODO: check keras imdb example

if not is_predict:
    # imdb.providers()返回两对data_provider。我想象的data_provider应该是一个接口:
    # batch(batch_size)
    # 另外提供helper，把list和numpy array包装成data provider：dataprovider.from_list(), dataprovider.from_np_array()
    # 任何一个带有以上接口的object都可以当作data provider。这样用户也很方便写自己的data_provider。
    # 我觉得现有的完形填空式的data_provider不是很必要：
    # - 不是非常直观，新手不大知道是啥意思。
    # - datalayer的名字写在了dataprovider里面，我觉得不需要这样的耦合。
    #   yield {
    #       'word': word_slot,
    #       'label': label
    #   }

    (x_train, y_train), (x_test, y_test) = imdb.providers()
    # 现在参数是放在一个paddle.trainer_config_helpers.settings这个字典里。用法如下：
    # settings(
    # batch_size=128,
    # learning_rate=2e-3,
    # learning_method=AdamOptimizer(),
    # regularization=L2Regularization(8e-4),
    # gradient_clipping_threshold=25)
    # 我觉得我们最好不要通过全局变量settings传参，我想到的坏处有这几点
    # - 很难追溯谁使用了这个全局变量，以及这个全局变量是否生效。比如这个[issue](https://github.com/PaddlePaddle/Paddle/issues/1139)
    # - settings包含了不同东西的设定混在一起，比如learning_method不是adam的时候，adam_epsilon这个参数没有用。
    lbl = data_layer("label", 2) # 不知道为何现在用的是data_layer("label", 1)，我觉得第二个参数应该是数据维度，所以应该是2。
    loss = classification_cost(input=output, label=lbl)

    optimizer = AdamOptimizer(
        output
        learning_rate=2e-3,
        regularization=L2Regularization(8e-4),
        gradient_clipping_threshold=25,
    )

    training_provider = {
        "word": X_train,
        "label": Y_train,
    }

    testing_provider = {
        "word": X_test,
        "label": Y_train,
    }
    
    # model是一个模块
    model.fit(optimizer, training_provider, batch_size=128, nb_epoch=5, validation_data=testing_provider)
    score = model.evaluate(loss, testing_provider, X_test, Y_test)
    print("score:", score)
else:
    predict_batch = {
        "word": X_test.batch(128),
    }
    # 所有的layer都有eval这个函数，算截止到这个layer的forward。比如画中间结果图的时候就可以用。
    out = output.eval(predict_batch)
