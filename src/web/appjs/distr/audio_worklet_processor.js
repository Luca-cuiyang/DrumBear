class MuseDriverProcessor extends AudioWorkletProcessor {
    constructor(options) {
        super(options)

        this.rpcPort = null
        this.channelInited = false
        this.audioRequested = false
        this.buffer = []

        this.port.onmessage = (event) => {
            if (event.data.type === 'INITIALIZE_DRIVER') {
                this.init(event.data)
            }
        }
    }

    init(data) {
        this.rpcPort = data.rpcPort
        this.rpcPort.onmessage = (event) => this.onMessageFromEngine(event.data)
        this.port.postMessage({ type: 'DRIVER_INITED' })
    }

    onMessageFromEngine(data) {
        if (data.type === 'channel_inited') {
            this.channelInited = true
            return
        }

        if (data.type === 'response_audio') {
            this.buffer.push(...data.data)
            this.audioRequested = false
        }
    }

    requestAudio() {
        if (!this.channelInited || this.audioRequested) {
            return
        }

        this.audioRequested = true
        this.rpcPort.postMessage({
            type: 'request_audio',
            samplesPerChannel: 1024
        })
    }

    process(inputs, outputs) {
        const output = outputs[0]
        const samplesPerChannel = output[0].length
        const totalSamples = samplesPerChannel * output.length

        if (this.buffer.length < totalSamples) {
            this.requestAudio()
        }

        for (let channelIndex = 0; channelIndex < output.length; channelIndex++) {
            const channel = output[channelIndex]
            for (let sampleIndex = 0; sampleIndex < samplesPerChannel; sampleIndex++) {
                const sourceIndex = sampleIndex * output.length + channelIndex
                channel[sampleIndex] = sourceIndex < this.buffer.length
                    ? this.buffer[sourceIndex]
                    : 0
            }
        }

        if (this.buffer.length >= totalSamples) {
            this.buffer = this.buffer.slice(totalSamples)
        } else {
            this.buffer = []
        }

        if (this.buffer.length < totalSamples * 4) {
            this.requestAudio()
        }

        return true
    }
}

registerProcessor('musedriver-processor', MuseDriverProcessor)
